"""
BAP /api/pipeline — execute a multi-agent pipeline via per-step Beckn contracts.

Each agent in the pipeline gets its own full Beckn transaction
(select → init → confirm → status) targeting the correct BPP.
Steps within the same execution layer run in parallel.

Flow:
    Frontend ─► POST /api/pipeline/run
                  │
                  ├─ Rebuild agent_catalog from on_discover callbacks
                  ├─ Build pipeline plan (bridge: layers, input_mapping, BPP routing)
                  ├─ For each execution layer:
                  │    For each step (parallel within layer):
                  │      select → on_select → init → on_init
                  │      → confirm(agent_input) → on_confirm
                  │      → poll status → extract result
                  │      → stash output for downstream steps
                  ├─ Assemble final output
                  └─► PipelineRunResponse { pipeline_id, status, steps, result }
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.bridge import build_pipeline_plan
from app.config import BAP_CALLER_URL, BAP_ID, BAP_URI, BPP_ID, BPP_URI, NETWORK_ID
from app.store import get_last_callback, create_draft_contract, set_transaction_target
from beckn_models.planning import Plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-pipeline"])


# ── Request / Response models ────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    plan: Plan
    prompt: str
    user_input: dict[str, Any]
    transaction_ids: list[str]
    bpp_id: str | None = None
    bpp_uri: str | None = None


class StepResult(BaseModel):
    step_id: str
    agent_id: str
    agent_name: str
    bpp_id: str
    transaction_id: str
    status: str  # COMPLETED | FAILED | SKIPPED
    duration_ms: int = 0
    output: Any | None = None
    error: str | None = None


class PipelineRunResponse(BaseModel):
    pipeline_id: str
    status: str  # COMPLETED | PARTIAL | FAILED
    steps: list[StepResult]
    result: dict[str, Any] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_context(action: str, txn_id: str, bpp_id: str, bpp_uri: str) -> dict:
    return {
        "networkId": NETWORK_ID,
        "action": action,
        "version": "2.0.0",
        "bapId": BAP_ID,
        "bapUri": BAP_URI,
        "bppId": bpp_id,
        "bppUri": bpp_uri,
        "transactionId": txn_id,
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
        "schemaContext": [],
    }


async def _send_to_onix(action: str, payload: dict) -> dict:
    url = f"{BAP_CALLER_URL}/{action}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
        logger.info("→ %s sent to %s — HTTP %d", action, url, resp.status_code)
        try:
            return resp.json()
        except Exception:
            return {"message": {"ack": {"status": "ACK"}}}


async def _wait_for_callback(
    txn_id: str,
    action: str,
    after_id: int = 0,
    max_attempts: int = 20,
    interval: float = 1.0,
) -> dict | None:
    """Poll callbacks table until we see the expected action with id > after_id."""
    for _ in range(max_attempts):
        cb = await get_last_callback(transaction_id=txn_id)
        if cb and cb.get("action") == action and cb.get("id", 0) > after_id:
            return cb
        await asyncio.sleep(interval)
    return None


def _parse_message(cb: dict) -> dict:
    """Extract message dict from a callback, handling JSON string encoding."""
    msg = cb.get("message", {})
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            msg = {}
    return msg if isinstance(msg, dict) else {}


def _extract_result(msg: dict) -> Any:
    """Extract the agent's result from an on_status message.

    Handles both Tecla (dict) and Serg (JSON string) response formats.
    Based on demo/runner.py _extract_result_payload().
    """
    contract = msg.get("contract", {})
    perf_list = contract.get("performance", [])
    if not perf_list:
        return None

    pa = perf_list[0].get("performanceAttributes", {})
    result = pa.get("result")

    # Serg agents return result as JSON string
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            pass

    return result


def _resolve_input(
    step: dict,
    user_input: dict[str, Any],
    completed_outputs: dict[str, Any],
) -> dict[str, Any]:
    """Translate input_mapping references to actual values.

    Planner syntax:
        $pipeline_input.field  → user_input[field]
        $steps.s1.field        → completed_outputs["s1"][field]
        anything else          → literal value
    """
    mapping = step.get("input_mapping", {})
    resolved: dict[str, Any] = {}

    for key, source in mapping.items():
        if not isinstance(source, str):
            resolved[key] = source
            continue

        if source.startswith("$pipeline_input."):
            field = source[len("$pipeline_input."):]
            value = user_input.get(field)
            if value is None:
                # Planner may use field names like "pdf", "file", "doc" that
                # don't exist in user_input. Try common content aliases so the
                # agent receives actual data instead of the literal template string.
                for alias in ("document", "text", "prompt"):
                    value = user_input.get(alias)
                    if value:
                        break
            resolved[key] = value if value is not None else ""
        elif source.startswith("$steps."):
            # "$steps.s1.summary" → completed_outputs["s1"]["summary"]
            rest = source[len("$steps."):]
            parts = rest.split(".", 1)
            if len(parts) == 2:
                step_id, field = parts
                step_output = completed_outputs.get(step_id)
                if isinstance(step_output, dict):
                    resolved[key] = step_output.get(field, source)
                else:
                    resolved[key] = source
            else:
                resolved[key] = source
        else:
            resolved[key] = source

    return resolved


# ── Agent catalog extraction from discover ────────────────────────────────────

def _extract_agent_catalog(callback: dict) -> dict[str, dict]:
    """Extract agent_id → {resourceAttributes, bpp_id, bpp_uri, offer_id} from on_discover."""
    msg = _parse_message(callback)
    catalog_data: dict[str, dict] = {}

    for catalog in msg.get("catalogs", []):
        # BPP routing info from catalog-level provider block
        provider = catalog.get("provider", {})
        bpp_id = provider.get("id", "")
        endpoints = provider.get("endpoints", {})
        bpp_uri = endpoints.get("beckn", "")

        # Map offer_id to resource IDs
        offer_map: dict[str, str] = {}
        for offer in catalog.get("offers", []):
            oid = offer.get("id", "")
            for rid in offer.get("resourceIds", []):
                offer_map[rid] = oid

        for resource in catalog.get("resources", []):
            agent_id = resource.get("id", "")
            ra = resource.get("resourceAttributes", {})
            if agent_id and ra:
                catalog_data[agent_id] = {
                    "resourceAttributes": ra,
                    "bpp_id": bpp_id,
                    "bpp_uri": bpp_uri,
                    "offer_id": offer_map.get(agent_id, f"offer-{agent_id}"),
                }

    return catalog_data


# ── Single step execution ─────────────────────────────────────────────────────

async def _execute_step(
    step: dict,
    user_input: dict[str, Any],
    completed_outputs: dict[str, Any],
    *,
    pipeline_prompt: str = "",
) -> StepResult:
    """Run one step through the full Beckn lifecycle: select → init → confirm → status."""
    step_id = step["id"]
    agent_id = step["agent_id"]
    agent_name = step.get("agent_name", agent_id)
    bpp_id = step["bpp_id"] or BPP_ID
    bpp_uri = step["bpp_uri"] or BPP_URI
    offer_id = step["offer_id"]

    t0 = time.time()
    txn_id = str(uuid.uuid4())

    def _elapsed() -> int:
        return int((time.time() - t0) * 1000)

    def _fail(reason: str) -> StepResult:
        logger.warning("pipeline step %s failed: %s", step_id, reason)
        return StepResult(
            step_id=step_id, agent_id=agent_id, agent_name=agent_name,
            bpp_id=bpp_id, transaction_id=txn_id,
            status="FAILED", duration_ms=_elapsed(), error=reason,
        )

    # ── Resolve input ─────────────────────────────────────────────────
    agent_input = _resolve_input(step, user_input, completed_outputs)

    # Safety net: if resolution produced no prompt-like key, inject the
    # pipeline-level prompt so agents always have something to work with.
    _PROMPT_KEYS = {"prompt", "text", "code", "document"}
    if pipeline_prompt and not (set(agent_input) & _PROMPT_KEYS):
        agent_input["prompt"] = pipeline_prompt

    logger.info("pipeline[%s] resolved input: %s", step_id, json.dumps(agent_input, ensure_ascii=False)[:200])

    # ── SELECT ────────────────────────────────────────────────────────
    contract_code = f"step-{step_id}-{txn_id[:8]}"
    set_transaction_target(txn_id, bpp_id, bpp_uri)

    commitments = [{
        "id": f"commitment-{step_id}",
        "status": {"code": "DRAFT"},
        "resources": [{
            "id": agent_id,
            "descriptor": {"name": agent_name, "code": agent_id},
            "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
        }],
        "offer": {"id": offer_id, "resourceIds": [agent_id]},
    }]
    participants = [{"id": "participant-buyer-001", "descriptor": {"name": "Pipeline", "code": "buyer"}}]

    await create_draft_contract(txn_id, contract_code, commitments, participants)

    select_resp = await _send_to_onix("select", {
        "context": _build_context("select", txn_id, bpp_id, bpp_uri),
        "message": {"contract": {"id": contract_code, "participants": participants, "commitments": commitments}},
    })

    on_select = await _wait_for_callback(txn_id, "on_select")
    if not on_select:
        return _fail("Timed out waiting for on_select")
    last_id = on_select.get("id", 0)

    # ── INIT ──────────────────────────────────────────────────────────
    await _send_to_onix("init", {
        "context": _build_context("init", txn_id, bpp_id, bpp_uri),
        "message": {"contract": {
            "commitments": commitments,
            "participants": participants,
            "performance": [{"id": f"perf-{step_id}"}],
            "settlements": [{"id": f"settlement-{step_id}", "status": "DRAFT"}],
        }},
    })

    on_init = await _wait_for_callback(txn_id, "on_init", after_id=last_id)
    if not on_init:
        return _fail("Timed out waiting for on_init")
    last_id = on_init.get("id", 0)

    # ── CONFIRM ───────────────────────────────────────────────────────
    # Enrich performanceAttributes so BPP can build a proper orchestrator2
    # mini-plan with step context, schemas, and the original prompt.
    confirm_commitments = [{
        **commitments[0],
        "status": {"descriptor": {"code": "DRAFT"}},
        "performanceAttributes": {
            "agent_input": agent_input,
            "task_description": f'{pipeline_prompt}. Step {step_id} ({step.get("skill_id", "")}): use agent {agent_name} to process the provided data.',
            "prompt": pipeline_prompt,
            "input_schema": step.get("input_schema"),
            "output_schema": step.get("output_schema"),
        },
    }]

    await _send_to_onix("confirm", {
        "context": _build_context("confirm", txn_id, bpp_id, bpp_uri),
        "message": {"contract": {
            "id": contract_code,
            "commitments": confirm_commitments,
            "participants": participants,
            "performance": [{"id": f"perf-{step_id}"}],
            "settlements": [{"id": f"settlement-{step_id}", "status": "COMPLETE"}],
        }},
    })

    on_confirm = await _wait_for_callback(txn_id, "on_confirm", after_id=last_id)
    if not on_confirm:
        return _fail("Timed out waiting for on_confirm")
    last_id = on_confirm.get("id", 0)

    # ── STATUS POLL ───────────────────────────────────────────────────
    status_commitments = [{
        **commitments[0],
        "status": {"descriptor": {"code": "ACTIVE"}},
    }]
    for attempt in range(30):
        await _send_to_onix("status", {
            "context": _build_context("status", txn_id, bpp_id, bpp_uri),
            "message": {"contract": {"id": contract_code, "commitments": status_commitments}},
        })

        on_status = await _wait_for_callback(txn_id, "on_status", after_id=last_id, max_attempts=4, interval=0.5)
        if on_status:
            last_id = on_status.get("id", 0)
            msg = _parse_message(on_status)
            contract = msg.get("contract", {})
            perf = (contract.get("performance") or [{}])[0]
            status_code = (perf.get("status", {}).get("code") or
                           perf.get("performanceAttributes", {}).get("status") or
                           "PENDING")

            if status_code == "COMPLETED":
                result = _extract_result(msg)
                logger.info("pipeline[%s] completed: %s", step_id, json.dumps(result, ensure_ascii=False)[:200] if result else "(empty)")
                return StepResult(
                    step_id=step_id, agent_id=agent_id, agent_name=agent_name,
                    bpp_id=bpp_id, transaction_id=txn_id,
                    status="COMPLETED", duration_ms=_elapsed(), output=result,
                )
            elif status_code == "FAILED":
                short_desc = perf.get("status", {}).get("shortDesc", "Agent failed")
                return _fail(f"Agent reported FAILED: {short_desc}")

        await asyncio.sleep(2)

    return _fail("Timed out waiting for terminal on_status")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(req: PipelineRunRequest):
    """Execute a multi-agent pipeline with per-step Beckn contracts."""
    pipeline_id = str(uuid.uuid4())

    # ── 1. Rebuild agent catalog from on_discover callbacks ───────────
    agent_catalog: dict[str, dict] = {}
    for txn_id in req.transaction_ids:
        cb = await get_last_callback(transaction_id=txn_id)
        if cb and cb.get("action") == "on_discover":
            agent_catalog.update(_extract_agent_catalog(cb))

    if not agent_catalog:
        raise HTTPException(status_code=422, detail="No agent catalog from discover. Re-run /api/plan.")

    missing = [s.recommended.agent_id for s in req.plan.steps if s.recommended.agent_id not in agent_catalog]
    if missing:
        raise HTTPException(status_code=422, detail=f"Agents not found in catalog: {missing}")

    # ── 2. Build pipeline plan ────────────────────────────────────────
    # Enrich user_input so common $pipeline_input.* references always
    # resolve regardless of which field name the planner LLM picks.
    # Explicit user_input keys take precedence over these defaults.
    enriched_input: dict[str, Any] = {
        "prompt": req.prompt,
        "text": req.prompt,
        "document": req.prompt,
    }
    enriched_input.update(req.user_input)

    pipeline_plan = build_pipeline_plan(req.plan, agent_catalog, enriched_input)
    steps_by_id = {s["id"]: s for s in pipeline_plan["steps"]}
    layers = pipeline_plan["execution_layers"]

    logger.info("pipeline %s: %d steps, %d layers", pipeline_id[:8], len(steps_by_id), len(layers))

    # ── 3. Execute layers ─────────────────────────────────────────────
    completed_outputs: dict[str, Any] = {}
    all_results: list[StepResult] = []

    for layer_idx, layer_ids in enumerate(layers):
        logger.info("pipeline %s: layer %d → %s", pipeline_id[:8], layer_idx, layer_ids)

        # Check for skipped steps (dependency failed)
        runnable = []
        for sid in layer_ids:
            step = steps_by_id[sid]
            failed_deps = [d for d in step["depends_on"] if d not in completed_outputs]
            if failed_deps:
                all_results.append(StepResult(
                    step_id=sid, agent_id=step["agent_id"], agent_name=step.get("agent_name", ""),
                    bpp_id=step["bpp_id"], transaction_id="",
                    status="SKIPPED", error=f"Dependency failed: {failed_deps}",
                ))
                continue
            runnable.append(step)

        # Execute runnable steps in parallel
        if runnable:
            results = await asyncio.gather(*[
                _execute_step(step, enriched_input, completed_outputs, pipeline_prompt=req.prompt)
                for step in runnable
            ])
            for r in results:
                all_results.append(r)
                if r.status == "COMPLETED" and r.output is not None:
                    # Orchestrator2 wraps the final result in {"raw": original, "response": "..."}
                    # after the synthesize step. Unwrap so downstream steps can resolve
                    # $steps.sN.field references against the actual agent output fields,
                    # not the synthesize envelope.
                    output = r.output
                    if isinstance(output, dict) and "raw" in output and isinstance(output.get("raw"), dict):
                        output = output["raw"]
                    completed_outputs[r.step_id] = output

    # ── 4. Assemble final output ──────────────────────────────────────
    statuses = {r.status for r in all_results}
    if statuses == {"COMPLETED"}:
        overall = "COMPLETED"
    elif "COMPLETED" in statuses:
        overall = "PARTIAL"
    else:
        overall = "FAILED"

    # Final result = all completed step outputs merged
    final_result = {}
    for r in all_results:
        if r.status == "COMPLETED" and isinstance(r.output, dict):
            final_result.update(r.output)

    logger.info("pipeline %s: %s (%d/%d steps completed)",
                pipeline_id[:8], overall,
                sum(1 for r in all_results if r.status == "COMPLETED"),
                len(all_results))

    return PipelineRunResponse(
        pipeline_id=pipeline_id,
        status=overall,
        steps=all_results,
        result=final_result if final_result else None,
    )
