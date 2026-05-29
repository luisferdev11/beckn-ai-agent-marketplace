"""
BAP /api/plan — orchestrates the two-phase planner.

Flow:
    Frontend ─► /api/plan
                  │
                  ├─► planner /extract-skills       (LLM #1)
                  │
                  ├─► for each skill in parallel:
                  │     POST /bap/caller/discover   (async Beckn)
                  │     poll callbacks table for on_discover
                  │     parse catalogs.resources → AgentCandidate[]
                  │
                  ├─► planner /compose-pipeline     (LLM #2 + validator + retry)
                  │
                  └─► PlanResponse

Rate-limited (slowapi). Each /plan call burns LLM tokens.

NOTE: do NOT add ``from __future__ import annotations`` here. The route uses
``req: PlanRequest = Body(...)`` and FastAPI builds a Pydantic ``TypeAdapter``
for that annotation; with the future import the annotation is stored as the
string ``"PlanRequest"`` (forward ref) and Pydantic fails with
``PydanticUserError: not fully defined``. Inference without ``Body(...)``
handles forward refs fine, but slowapi's decorator broke inference, which is
why we use ``Body(...)`` — hence: no future import in this file.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Body, HTTPException, Request

from app.config import (
    BAP_CALLER_URL,
    BAP_ID,
    BAP_URI,
    BPP_ID,
    BPP_URI,
    DISCOVER_TIMEOUT_S,
    NETWORK_ID,
    PLAN_RATE_LIMIT,
    PLANNER_TIMEOUT_S,
    PLANNER_URL,
)
from app.limiter import limiter
from app.store import get_last_callback
from beckn_models.planning import (
    AgentCandidate,
    ComposeRequest,
    ExtractSkillsRequest,
    ExtractSkillsResponse,
    Plan,
    PlanRequest,
    PlanResponse,
    SkillRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-plan"])


# ── Planner HTTP client ──────────────────────────────────────

async def _call_planner(path: str, payload: dict) -> dict:
    """POST to the planner service and surface clear errors to the caller."""
    url = f"{PLANNER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=PLANNER_TIMEOUT_S) as client:
            resp = await client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"PLANNER_TIMEOUT: {exc}")
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail=f"PLANNER_UNREACHABLE: {exc}")

    if resp.status_code == 422:
        # Business error from the planner (e.g. INVALID_PLAN, unknown skill)
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=422, detail=detail)
    if resp.status_code >= 500:
        raise HTTPException(status_code=503, detail=f"PLANNER_ERROR: HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


# ── Discover helpers ─────────────────────────────────────────

def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_discover_context(txn_id: str) -> dict:
    return {
        "networkId": NETWORK_ID,
        "action": "discover",
        "version": "2.0.0",
        "bapId": BAP_ID,
        "bapUri": BAP_URI,
        "bppId": BPP_ID,
        "bppUri": BPP_URI,
        "transactionId": txn_id,
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
        "schemaContext": [],
    }


async def _discover_skill(skill: SkillRequest) -> tuple[str, list[AgentCandidate]]:
    """
    Run a single discover for one skill, wait for the on_discover callback,
    parse and return the candidates. Returns (txn_id, candidates).
    """
    txn_id = str(uuid.uuid4())
    ctx = _build_discover_context(txn_id)

    # The LLM's `description` is the semantic query — it's a rich, catalog-
    # friendly sentence built precisely for embedding search. We send it as
    # intent.textSearch and let the CDS's vector search do the work.
    # We do NOT mix in skill_id or reason: description is intentionally
    # written by the LLM to be the best single search string.
    intent: dict = {"textSearch": skill.description}

    # Carry skill_id + filters as schemaContext hints (harmless metadata —
    # mock-network ignores them when textSearch is non-empty, but some CDS
    # implementations may use them for additional filtering or analytics).
    hints: list[str] = [f"category:{skill.skill_id}"]
    for key, value in skill.filters.items():
        if isinstance(value, list):
            for item in value:
                hints.append(f"filter:{key}={item}")
        else:
            hints.append(f"filter:{key}={value}")
    ctx["schemaContext"] = hints

    payload = {"context": ctx, "message": {"intent": intent}}

    # Fire-and-forget the discover request. The callback arrives via the
    # webhook router and lands in the callbacks table.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{BAP_CALLER_URL}/discover", json=payload)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error(f"discover for skill={skill.skill_id} failed to dispatch: {exc}")
        return txn_id, []

    cb = await _wait_for_callback(txn_id, "on_discover", timeout_s=DISCOVER_TIMEOUT_S)
    if cb is None:
        logger.warning(f"discover for skill={skill.skill_id} timed out (txn={txn_id[:8]})")
        return txn_id, []

    return txn_id, _parse_candidates(cb)


async def _wait_for_callback(
    txn_id: str,
    action: str,
    timeout_s: float,
    interval_s: float = 0.5,
) -> dict | None:
    """Poll the callbacks table until we see a matching callback or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        cb = await get_last_callback(transaction_id=txn_id)
        if cb and cb.get("action") == action:
            return cb
        await asyncio.sleep(interval_s)
    return None


def _parse_candidates(callback: dict) -> list[AgentCandidate]:
    """Transform on_discover catalogs.resources[] into AgentCandidate[].

    Mirrors the transformation in services/frontend/src/lib/beckn-api.ts:175.
    """
    msg = callback.get("message")
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            return []
    if not isinstance(msg, dict):
        return []

    catalogs = msg.get("catalogs") or []
    if not catalogs:
        return []

    candidates: list[AgentCandidate] = []
    for catalog in catalogs:
        for resource in catalog.get("resources", []):
            ra = resource.get("resourceAttributes") or {}
            skills_raw = ra.get("skills") or []
            pricing = ra.get("pricing") or {}
            sla = ra.get("sla") or {}
            provider_obj = ra.get("provider") or {}
            provider_name = provider_obj.get("name") if isinstance(provider_obj, dict) else None

            input_modes: set[str] = set()
            output_modes: set[str] = set()
            languages: set[str] = set()
            skill_ids: list[str] = []
            for s in skills_raw:
                if not isinstance(s, dict):
                    continue
                if s.get("id"):
                    skill_ids.append(s["id"])
                for m in s.get("inputModes") or []:
                    input_modes.add(m)
                for m in s.get("outputModes") or []:
                    output_modes.add(m)
                for lang in s.get("supportedLanguages") or []:
                    languages.add(lang)

            descriptor = resource.get("descriptor") or {}
            name = ra.get("label") or descriptor.get("name") or "Unnamed"

            try:
                pricing_value = float(pricing.get("value") or 0)
            except (TypeError, ValueError):
                pricing_value = 0.0

            try:
                latency_ms = int(sla.get("maxLatencyMs") or 0)
            except (TypeError, ValueError):
                latency_ms = 0

            accuracy: float | None = None
            if "accuracy" in sla:
                try:
                    accuracy = float(sla["accuracy"])
                except (TypeError, ValueError):
                    accuracy = None

            candidates.append(AgentCandidate(
                agent_id=resource.get("id", ""),
                name=str(name),
                provider=str(provider_name or "Unknown"),
                skill_ids=skill_ids,
                input_modes=sorted(input_modes),
                output_modes=sorted(output_modes),
                supported_languages=sorted(languages),
                input_schema=ra.get("inputSchema") or ra.get("input_schema"),
                output_schema=ra.get("outputSchema") or ra.get("output_schema"),
                pricing_value=pricing_value,
                pricing_currency=str(pricing.get("currency") or "USD"),
                pricing_model=str(pricing.get("model") or pricing.get("type") or "per_task"),
                max_latency_ms=latency_ms,
                accuracy=accuracy,
                jurisdiction=ra.get("jurisdiction"),
            ))
    return candidates


# ── Endpoint ─────────────────────────────────────────────────

@router.post("/plan", response_model=PlanResponse)
@limiter.limit(PLAN_RATE_LIMIT)
async def plan_endpoint(
    request: Request,
    req: PlanRequest = Body(...),
) -> PlanResponse:
    """Orchestrate planner phases 1 and 3 with a parallel discover loop in between.

    NOTE: ``req: PlanRequest = Body(...)`` is required because slowapi's
    ``@limiter.limit`` decorator wraps the function and FastAPI then fails to
    infer that the Pydantic model belongs to the request body — it falls back
    to treating it as a query parameter, which makes every call return 422.
    """
    txn_ids: list[str] = []

    # ─── Phase 1: extract skills ──────────────────────────────
    extract_req = ExtractSkillsRequest(
        prompt=req.prompt,
        input_format=req.input_format,
        output_format=req.output_format,
    )
    extract_raw = await _call_planner("/extract-skills", extract_req.model_dump())
    extract_resp = ExtractSkillsResponse.model_validate(extract_raw)

    if not extract_resp.skills_needed:
        return PlanResponse(
            plan=None,
            error="No skills identified for the given prompt",
            transaction_ids=txn_ids,
        )

    # ─── Phase 2: parallel discover per skill ─────────────────
    discover_tasks = [_discover_skill(s) for s in extract_resp.skills_needed]
    discover_results = await asyncio.gather(*discover_tasks, return_exceptions=True)

    candidates_per_skill: dict[str, list[AgentCandidate]] = {}
    empty_skills: list[str] = []
    for skill, result in zip(extract_resp.skills_needed, discover_results):
        if isinstance(result, BaseException):
            logger.error(f"discover for skill={skill.skill_id}: {result!r}")
            empty_skills.append(skill.skill_id)
            continue
        txn_id, candidates = result
        txn_ids.append(txn_id)
        if not candidates:
            empty_skills.append(skill.skill_id)
        else:
            # If the planner picked the same skill_id twice (unlikely but possible),
            # we merge candidate lists.
            candidates_per_skill.setdefault(skill.skill_id, []).extend(candidates)

    if empty_skills:
        return PlanResponse(
            plan=None,
            error=f"No candidates found for skill(s): {sorted(set(empty_skills))}",
            transaction_ids=txn_ids,
        )

    # ─── Phase 3: compose pipeline ────────────────────────────
    compose_req = ComposeRequest(prompt=req.prompt, candidates=candidates_per_skill)
    plan_raw = await _call_planner("/compose-pipeline", compose_req.model_dump())
    plan = Plan.model_validate(plan_raw)

    return PlanResponse(plan=plan, error=None, transaction_ids=txn_ids)
