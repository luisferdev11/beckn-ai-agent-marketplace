"""
BAP /api/pipeline — run a multi-agent pipeline through a single Beckn contract.

Flow:
    Frontend ─► POST /api/pipeline/run
                  │
                  ├─ Re-read on_discover callbacks → build agent_facts index
                  ├─ Build bridge plan (Plan → orchestrator v2 format)
                  ├─ select (multi-resource commitment)
                  ├─ wait on_select
                  ├─ init
                  ├─ wait on_init
                  ├─ confirm  (performanceAttributes.pipeline_plan = bridge plan)
                  ├─ wait on_confirm
                  └─► { transaction_id, contract }

Frontend then polls /api/contracts/status as usual.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.bridge import build_orchestrator2_plan
from app.config import BAP_CALLER_URL, BAP_ID, BAP_URI, BPP_ID, BPP_URI, NETWORK_ID
from app.store import (
    get_last_callback,
    create_draft_contract,
    set_transaction_target,
)
from beckn_models.planning import Plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-pipeline"])

CALLBACK_TIMEOUT_S = 15.0
CALLBACK_POLL_INTERVAL_S = 0.5


# ── Request / Response models ────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    plan: Plan
    prompt: str
    user_input: dict[str, Any]
    transaction_ids: list[str]
    bpp_id: str | None = None
    bpp_uri: str | None = None


class PipelineRunResponse(BaseModel):
    transaction_id: str
    contract: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_context(
    action: str,
    txn_id: str,
    bpp_id: str | None = None,
    bpp_uri: str | None = None,
) -> dict:
    return {
        "networkId": NETWORK_ID,
        "action": action,
        "version": "2.0.0",
        "bapId": BAP_ID,
        "bapUri": BAP_URI,
        "bppId": bpp_id or BPP_ID,
        "bppUri": bpp_uri or BPP_URI,
        "transactionId": txn_id,
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
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
    timeout_s: float = CALLBACK_TIMEOUT_S,
) -> dict | None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        cb = await get_last_callback(transaction_id=txn_id)
        if cb and cb.get("action") == action:
            return cb
        await asyncio.sleep(CALLBACK_POLL_INTERVAL_S)
    return None


def _extract_agent_facts(callback: dict) -> dict[str, dict]:
    """Extract agent_id → resourceAttributes from an on_discover callback."""
    msg = callback.get("message")
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            return {}
    if not isinstance(msg, dict):
        return {}

    facts: dict[str, dict] = {}
    for catalog in msg.get("catalogs", []):
        for resource in catalog.get("resources", []):
            agent_id = resource.get("id", "")
            ra = resource.get("resourceAttributes", {})
            if agent_id and ra:
                facts[agent_id] = ra
    return facts


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(req: PipelineRunRequest):
    """Execute a multi-agent pipeline through one Beckn v2 contract.

    1. Rebuild agent_facts from stored on_discover callbacks
    2. Build the bridge plan (Plan → orchestrator v2 format)
    3. Run select → init → confirm with the pipeline plan embedded
    4. Return transaction_id so the frontend can poll /api/contracts/status
    """
    bpp_id = req.bpp_id or BPP_ID
    bpp_uri = req.bpp_uri or BPP_URI

    # ── 1. Rebuild agent_facts from on_discover callbacks ─────────────────
    agent_facts: dict[str, dict] = {}
    for txn_id in req.transaction_ids:
        cb = await get_last_callback(transaction_id=txn_id)
        if cb and cb.get("action") == "on_discover":
            agent_facts.update(_extract_agent_facts(cb))

    if not agent_facts:
        raise HTTPException(
            status_code=422,
            detail="Could not recover agent facts from discover callbacks. "
                   "Re-run /api/plan first.",
        )

    # Verify all recommended agents have facts
    missing = []
    for step in req.plan.steps:
        if step.recommended.agent_id not in agent_facts:
            missing.append(step.recommended.agent_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Agent facts not found for: {missing}. "
                   f"Available: {list(agent_facts.keys())}",
        )

    # ── 2. Build bridge plan ──────────────────────────────────────────────
    bridge_plan = build_orchestrator2_plan(
        plan=req.plan,
        agent_facts=agent_facts,
        user_input=req.user_input,
        prompt=req.prompt,
    )
    logger.info("bridge plan built: %d agents, %d steps, %d layers",
                len(bridge_plan["agents"]),
                len(bridge_plan["steps"]),
                len(bridge_plan["executionLayers"]))

    # ── 3. Beckn lifecycle: select → init → confirm ──────────────────────
    txn_id = str(uuid.uuid4())
    contract_code = f"pipeline-{txn_id[:8]}"
    set_transaction_target(txn_id, bpp_id, bpp_uri)

    # Collect all unique agent IDs for the multi-resource commitment
    agent_ids = [step.recommended.agent_id for step in req.plan.steps]
    resources = [
        {
            "id": aid,
            "descriptor": {"name": agent_facts.get(aid, {}).get("label", aid), "code": aid},
            "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
        }
        for aid in dict.fromkeys(agent_ids)  # preserve order, deduplicate
    ]

    participants = [
        {"id": "participant-buyer-001", "descriptor": {"name": "Pipeline User", "code": "buyer"}}
    ]
    commitments = [{
        "id": "commitment-pipeline-001",
        "descriptor": {"name": "Multi-Agent Pipeline", "code": "PIPELINE"},
        "status": {"code": "DRAFT"},
        "resources": resources,
        "offer": {
            "id": f"offer-pipeline-{txn_id[:8]}",
            "resourceIds": list(dict.fromkeys(agent_ids)),
        },
    }]

    await create_draft_contract(txn_id, contract_code, commitments, participants)

    # ── SELECT ────────────────────────────────────────────────────────
    select_payload = {
        "context": _build_context("select", txn_id, bpp_id, bpp_uri),
        "message": {
            "contract": {
                "id": contract_code,
                "participants": participants,
                "commitments": commitments,
            }
        },
    }
    await _send_to_onix("select", select_payload)
    on_select = await _wait_for_callback(txn_id, "on_select")
    if not on_select:
        raise HTTPException(status_code=504, detail="on_select callback timed out")

    # ── INIT ──────────────────────────────────────────────────────────
    init_payload = {
        "context": _build_context("init", txn_id, bpp_id, bpp_uri),
        "message": {
            "contract": {
                "commitments": commitments,
                "participants": participants,
                "performance": [{"id": "perf-pipeline-001"}],
                "settlements": [{"id": "settlement-pipeline-001", "status": "DRAFT"}],
            }
        },
    }
    await _send_to_onix("init", init_payload)
    on_init = await _wait_for_callback(txn_id, "on_init")
    if not on_init:
        raise HTTPException(status_code=504, detail="on_init callback timed out")

    # ── CONFIRM (with pipeline plan embedded) ─────────────────────────
    confirm_commitments = [{
        **commitments[0],
        "status": {"descriptor": {"code": "DRAFT"}},
        "performanceAttributes": {
            "pipeline_mode": True,
            "pipeline_plan": bridge_plan,
            "prompt": req.prompt,
            "user_input": req.user_input,
        },
    }]

    confirm_payload = {
        "context": _build_context("confirm", txn_id, bpp_id, bpp_uri),
        "message": {
            "contract": {
                "id": contract_code,
                "commitments": confirm_commitments,
                "participants": participants,
                "performance": [{"id": "perf-pipeline-001"}],
                "settlements": [{"id": "settlement-pipeline-001", "status": "COMPLETE"}],
            }
        },
    }
    await _send_to_onix("confirm", confirm_payload)
    on_confirm = await _wait_for_callback(txn_id, "on_confirm")
    if not on_confirm:
        raise HTTPException(status_code=504, detail="on_confirm callback timed out")

    # Parse contract from callback
    msg = on_confirm.get("message", {})
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            msg = {}
    contract = msg.get("contract", {}) if isinstance(msg, dict) else {}

    return PipelineRunResponse(transaction_id=txn_id, contract=contract)
