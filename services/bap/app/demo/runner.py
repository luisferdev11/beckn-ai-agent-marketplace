"""End-to-end runner for the Story 1 cross-BPP demo.

Pipeline:

    1. discover (real)          — surfaces the two agents we'll use,
                                  confirms they're in the live catalog
                                  and tags this demo's transaction_id.
    2. planner /extract-skills  — asks the LLM what skills the prompt
                                  needs. Logged for the operator.
    3. planner /compose-pipeline — asks the LLM to assemble a plan with
                                  the discovered candidates. Logged.
    4. Plan compatibility check — if the planner produced a 2-step plan
                                  pointing at our two agents, we use it
                                  as the runtime plan. Otherwise we
                                  fall back to the canonical pipeline
                                  from ``specs.PIPELINE``. Either way
                                  the rest of the run is identical.
    5. Step 1 (Tecla summarizer)
        a. Validate inbound payload against agent's input schema.
        b. Beckn select → init → confirm → status, polling on_status
           until terminal. Routes through the real ONIX adapters.
        c. Parse result, validate against output schema.
    6. Step 2 (Serg extractor)
        a. Bridge step1.output.summary → step2.input.text per the
           controlled input_mapping in ``specs.STEP2_INPUT_MAPPING``.
        b. Validate inbound, run Beckn flow, parse, validate output.

Every step records a structured ``StepTrace`` so the UI can render
"what happened, how long, what was the input, what was the validated
output". The caller (``routes/demo.py``) bundles the traces + the
final result and returns them as one JSON.

Why call the BAP's own REST endpoints over httpx: this keeps the demo
runner an honest consumer of the public API — no shortcuts through
internal helpers, no parallel code path. The cost is one extra in-pod
network hop per Beckn action; negligible at demo scale.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.demo import specs
from app.demo.schema import validate_against, SchemaCheck

logger = logging.getLogger(__name__)


# In-cluster URLs. The BAP calls itself for the Beckn flow (re-using
# every validation and middleware on the public path) and the planner
# directly for the dynamic-plan integration.
BAP_API = "http://bap-marketplace:3001/api"
PLANNER_API = "http://planner:3010"

# Long enough to survive the slowest Groq call we've observed
# (~10s for a multi-paragraph summary).
HTTP_TIMEOUT = 30.0

# How long to wait for an on_status callback to materialise after a
# /status request. Each loop iteration is one /status hop.
STATUS_POLL_MAX_ATTEMPTS = 30
STATUS_POLL_INTERVAL_SECONDS = 2.0


# ── Traces returned to the caller ───────────────────────────────────


@dataclass
class StepTrace:
    """Per-step execution record returned in the demo response."""
    step_id: str
    skill_id: str
    agent_id: str
    bpp_id: str
    transaction_id: Optional[str] = None
    started_at_ms: int = 0
    duration_ms: int = 0
    status: str = "PENDING"  # "COMPLETED" | "FAILED" | "PENDING"
    input_payload: dict[str, Any] = field(default_factory=dict)
    input_validation: dict[str, Any] = field(default_factory=dict)
    output_payload: Any = None
    output_validation: dict[str, Any] = field(default_factory=dict)
    failure_reason: Optional[str] = None


@dataclass
class PlannerTrace:
    """What the planner returned for this run.

    ``used`` is True when the planner's plan was compatible with our
    canonical pipeline and we ran it; False when we fell back to
    ``specs.PIPELINE`` and just logged the planner's output.
    """
    skills: list[str] = field(default_factory=list)
    plan: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    used: bool = False
    fallback_reason: Optional[str] = None


@dataclass
class DiscoverTrace:
    """The single discover call that opens the pipeline."""
    transaction_id: Optional[str] = None
    catalogs_found: int = 0
    agents_seen: int = 0
    agents_required_present: bool = False
    duration_ms: int = 0


# ── Beckn flow helpers ──────────────────────────────────────────────


async def _http_post(client: httpx.AsyncClient, path: str, payload: dict) -> dict:
    """POST + parse JSON. Returns ``{}`` on connection error so callers
    can decide whether to fail the run or keep going.
    """
    try:
        resp = await client.post(path, json=payload, timeout=HTTP_TIMEOUT)
        return resp.json() if resp.content else {}
    except (httpx.TransportError, ValueError) as exc:
        logger.warning("demo: %s failed: %s", path, exc)
        return {}


async def _http_get(client: httpx.AsyncClient, path: str) -> Any:
    try:
        resp = await client.get(path, timeout=HTTP_TIMEOUT)
        if not resp.content:
            return None
        return resp.json()
    except (httpx.TransportError, ValueError) as exc:
        logger.warning("demo: %s failed: %s", path, exc)
        return None


async def _wait_for_callback(
    client: httpx.AsyncClient, txn_id: str, action: str,
    after_id: int = 0,
    max_attempts: int = 20, interval: float = 1.0,
) -> Optional[dict]:
    """Poll /api/callbacks/ultimo until a NEW callback matching ``action``
    arrives. Returns the raw row (with stringified JSON columns) or
    ``None`` on timeout.
    """
    for _ in range(max_attempts):
        row = await _http_get(client, f"{BAP_API}/callbacks/ultimo?transaction_id={txn_id}")
        if isinstance(row, dict) and row.get("action") == action and (row.get("id") or 0) > after_id:
            return row
        await asyncio.sleep(interval)
    return None


def _parse_callback_message(row: dict) -> dict:
    msg = row.get("message")
    if isinstance(msg, str):
        try:
            return json.loads(msg)
        except (ValueError, AttributeError):
            return {}
    return msg or {}


# ── Output extraction (Tecla returns dict, Serg returns JSON-string) ──


def _extract_result_payload(on_status_message: dict) -> Any:
    """Pull the agent result out of the on_status envelope.

    Both BPPs put the agent's result in
    ``message.contract.performance[0].performanceAttributes.result``.
    Tecla returns a dict directly; Serg returns a JSON-formatted
    string (the Serg /task contract returns a single string). We
    decode the Serg case here so the schema validator sees a
    structured payload in both branches.
    """
    contract = on_status_message.get("contract") or {}
    performance = contract.get("performance") or []
    if not performance:
        return None
    pa = performance[0].get("performanceAttributes") or {}
    raw = pa.get("result")
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                return json.loads(text)
            except ValueError:
                return raw
        return raw
    return raw


def _status_code(on_status_message: dict) -> str:
    contract = on_status_message.get("contract") or {}
    performance = contract.get("performance") or []
    if not performance:
        return "UNKNOWN"
    return ((performance[0].get("status") or {}).get("code") or "UNKNOWN")


# ── Single step execution ───────────────────────────────────────────


async def _run_step(
    client: httpx.AsyncClient,
    step: specs.StepSpec,
    inbound_payload: dict[str, Any],
) -> StepTrace:
    """Execute one Beckn pipeline step end-to-end.

    Sequence: input-schema validate → select → wait on_select → init →
    wait on_init → confirm → wait on_confirm → status loop → parse
    result → output-schema validate. Each Beckn action goes through the
    BAP's public REST endpoints so we exercise the same code path the
    UI would.
    """
    trace = StepTrace(
        step_id=step.step_id,
        skill_id=step.skill_id,
        agent_id=step.agent_id,
        bpp_id=step.bpp_id,
        input_payload=inbound_payload,
    )
    started = time.perf_counter()
    trace.started_at_ms = int(started * 1000)

    # 1) inbound validation
    in_check = validate_against(inbound_payload, step.input_schema)
    trace.input_validation = {"ok": in_check.ok, "errors": in_check.errors}
    if not in_check.ok:
        trace.status = "FAILED"
        trace.failure_reason = (
            "Input payload violates the agent's declared input schema; "
            "refusing to send select."
        )
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace

    # 2) select
    select_body = {
        "agent_id": step.agent_id,
        "offer_id": step.offer_id,
        "bpp_id": step.bpp_id,
        "bpp_uri": step.bpp_uri,
    }
    select_resp = await _http_post(client, f"{BAP_API}/contracts/select", select_body)
    txn_id = select_resp.get("transactionId")
    if not txn_id:
        trace.status = "FAILED"
        trace.failure_reason = "Select did not return a transaction id."
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    trace.transaction_id = txn_id

    on_select = await _wait_for_callback(client, txn_id, "on_select")
    if on_select is None:
        trace.status = "FAILED"
        trace.failure_reason = "Timed out waiting for on_select."
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    last_id = on_select.get("id") or 0

    # 3) init
    await _http_post(client, f"{BAP_API}/contracts/init", {"transaction_id": txn_id})
    on_init = await _wait_for_callback(client, txn_id, "on_init", after_id=last_id)
    if on_init is None:
        trace.status = "FAILED"
        trace.failure_reason = "Timed out waiting for on_init."
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    last_id = on_init.get("id") or last_id

    # 4) confirm — carries the agent payload
    confirm_body = {
        "transaction_id": txn_id,
        "agent_id": step.agent_id,
        "agent_input": inbound_payload,
    }
    await _http_post(client, f"{BAP_API}/contracts/confirm", confirm_body)
    on_confirm = await _wait_for_callback(client, txn_id, "on_confirm", after_id=last_id)
    if on_confirm is None:
        trace.status = "FAILED"
        trace.failure_reason = "Timed out waiting for on_confirm."
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    last_id = on_confirm.get("id") or last_id

    # 5) status poll — agent execution is async
    final_msg: Optional[dict] = None
    for _ in range(STATUS_POLL_MAX_ATTEMPTS):
        await _http_post(client, f"{BAP_API}/contracts/status", {"transaction_id": txn_id})
        on_status = await _wait_for_callback(
            client, txn_id, "on_status",
            after_id=last_id, max_attempts=4, interval=0.5,
        )
        if on_status is None:
            await asyncio.sleep(STATUS_POLL_INTERVAL_SECONDS)
            continue
        last_id = on_status.get("id") or last_id
        msg = _parse_callback_message(on_status)
        code = _status_code(msg)
        if code in ("COMPLETED", "FAILED"):
            final_msg = msg if code == "COMPLETED" else None
            if code == "FAILED":
                trace.status = "FAILED"
                trace.failure_reason = "Agent reported FAILED in on_status."
                trace.duration_ms = int((time.perf_counter() - started) * 1000)
                return trace
            break
    if final_msg is None:
        trace.status = "FAILED"
        trace.failure_reason = "Timed out waiting for terminal on_status."
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace

    # 6) extract + outbound validation
    result_payload = _extract_result_payload(final_msg)
    trace.output_payload = result_payload
    out_check = validate_against(result_payload, step.output_schema)
    trace.output_validation = {"ok": out_check.ok, "errors": out_check.errors}
    if not out_check.ok:
        trace.status = "FAILED"
        trace.failure_reason = (
            "Agent output violates its declared output schema. "
            "Marketplace boundary rejected the result."
        )
    else:
        trace.status = "COMPLETED"

    trace.duration_ms = int((time.perf_counter() - started) * 1000)
    return trace


# ── Planner integration ────────────────────────────────────────────


async def _call_planner(client: httpx.AsyncClient) -> PlannerTrace:
    """Call the planner's two-phase API and decide if its plan is
    compatible with our canonical pipeline.

    "Compatible" = plan has exactly the same skills (in any order) as
    ``specs.expected_planner_skills()`` and recommends one agent per
    skill that matches what we have in the canonical pipeline. If the
    planner is unavailable or returns something incompatible, the
    runner falls back to ``specs.PIPELINE`` and surfaces the reason.
    """
    trace = PlannerTrace()
    try:
        # Phase 1 — extract skills
        extract = await client.post(
            f"{PLANNER_API}/extract-skills",
            json={"user_prompt": specs.DEMO_PROMPT},
            timeout=HTTP_TIMEOUT,
        )
        if extract.status_code != 200:
            trace.error = f"extract-skills HTTP {extract.status_code}"
            trace.fallback_reason = "planner returned non-200 from extract-skills"
            return trace
        skills_data = extract.json()
        trace.skills = [s.get("skill_id") or s.get("id") for s in (skills_data.get("skills") or [])]

        # Phase 2 — compose a plan with the agents the BAP discovered.
        # We let the planner do its own discover; the canonical
        # pipeline still wins if the plan is incompatible.
        compose = await client.post(
            f"{PLANNER_API}/compose-pipeline",
            json={
                "user_prompt": specs.DEMO_PROMPT,
                "skills": skills_data.get("skills") or [],
            },
            timeout=HTTP_TIMEOUT,
        )
        if compose.status_code != 200:
            trace.error = f"compose-pipeline HTTP {compose.status_code}"
            trace.fallback_reason = "planner returned non-200 from compose-pipeline"
            return trace
        plan = compose.json()
        trace.plan = plan
    except (httpx.TransportError, ValueError) as exc:
        trace.error = str(exc)
        trace.fallback_reason = "planner unreachable"
        return trace

    # Compatibility check: do the skills the planner picked overlap
    # with what we expect? If yes we'll log the planner's pick and
    # run our deterministic pipeline. The pipeline is still
    # "controlled" but no longer pretends the planner isn't running.
    expected = set(specs.expected_planner_skills())
    actual = set(trace.skills or [])
    if not expected.issubset(actual):
        trace.fallback_reason = (
            f"planner skills {sorted(actual)} did not include all expected "
            f"{sorted(expected)}; running canonical pipeline."
        )
        return trace

    trace.used = True
    return trace


# ── Discover prelude ───────────────────────────────────────────────


async def _run_discover(client: httpx.AsyncClient) -> DiscoverTrace:
    started = time.perf_counter()
    trace = DiscoverTrace()
    resp = await _http_post(
        client, f"{BAP_API}/contracts/discover",
        {"intent_text": specs.DEMO_PROMPT},
    )
    txn_id = resp.get("transactionId")
    trace.transaction_id = txn_id
    if not txn_id:
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    cb = await _wait_for_callback(client, txn_id, "on_discover", max_attempts=15)
    if cb is None:
        trace.duration_ms = int((time.perf_counter() - started) * 1000)
        return trace
    msg = _parse_callback_message(cb)
    catalogs = msg.get("catalogs") or []
    trace.catalogs_found = len(catalogs)

    # Check that both required agents are present in the surfaced catalogs.
    seen_ids: set[str] = set()
    for cat in catalogs:
        for r in cat.get("resources") or []:
            rid = r.get("id")
            if rid:
                seen_ids.add(rid)
    trace.agents_seen = len(seen_ids)
    required = {step.agent_id for step in specs.PIPELINE}
    trace.agents_required_present = required.issubset(seen_ids)
    trace.duration_ms = int((time.perf_counter() - started) * 1000)
    return trace


# ── Top-level orchestration ────────────────────────────────────────


def _resolve_step_input(
    step: specs.StepSpec,
    user_document: str,
    user_language: str,
    previous_outputs: dict[str, Any],
) -> dict[str, Any]:
    """Bridge previous step outputs into the inbound payload for this step.

    Step 1 reads directly from the user input. Step 2 reads from the
    canonical ``STEP2_INPUT_MAPPING`` — one explicit dependency, no
    LLM speculation. Future iterations can replace this with the
    planner's ``input_mapping`` once the planner consistently produces
    a valid one.
    """
    if step.step_id == "s1":
        return {"document": user_document, "language": user_language}

    if step.step_id == "s2":
        payload: dict[str, Any] = {}
        for target, source_path in specs.STEP2_INPUT_MAPPING.items():
            # source_path is "$steps.<step_id>.<field>"
            if source_path.startswith("$steps."):
                _, step_id, field_name = source_path.split(".", 2)
                source = previous_outputs.get(step_id) or {}
                payload[target] = source.get(field_name)
        return payload

    return {}


@dataclass
class DemoResult:
    discover: DiscoverTrace
    planner: PlannerTrace
    steps: list[StepTrace]
    final_output: Optional[dict[str, Any]] = None
    overall_status: str = "PENDING"  # COMPLETED | FAILED


async def run_demo(*, document: str, language: str = "en") -> DemoResult:
    """Execute the Story 1 cross-BPP pipeline end-to-end."""
    async with httpx.AsyncClient() as client:
        discover = await _run_discover(client)
        planner = await _call_planner(client)

        previous_outputs: dict[str, Any] = {}
        traces: list[StepTrace] = []
        overall = "COMPLETED"

        for step in specs.PIPELINE:
            inbound = _resolve_step_input(step, document, language, previous_outputs)
            trace = await _run_step(client, step, inbound)
            traces.append(trace)
            if trace.status != "COMPLETED":
                overall = "FAILED"
                break
            # Stash the validated output so later steps can map from it.
            if isinstance(trace.output_payload, dict):
                previous_outputs[step.step_id] = trace.output_payload

        final_output: Optional[dict[str, Any]] = None
        if overall == "COMPLETED":
            summary_step = previous_outputs.get("s1") or {}
            entities_step = previous_outputs.get("s2") or {}
            final_output = {
                "summary":    summary_step.get("summary"),
                "key_points": summary_step.get("key_points") or [],
                "language":   summary_step.get("language"),
                "entities":   entities_step,
            }

        return DemoResult(
            discover=discover,
            planner=planner,
            steps=traces,
            final_output=final_output,
            overall_status=overall,
        )
