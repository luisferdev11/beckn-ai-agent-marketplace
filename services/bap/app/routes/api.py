"""
BAP API routes — the active side that originates Beckn transactions.

These endpoints are called by the frontend (or scripts/tests) to trigger
Beckn actions. The BAP builds the Beckn payload and POSTs it to
ONIX-BAP at /bap/caller/{action}.

Key improvement: init/confirm use stored data from on_select instead of
hardcoding values. The flow is:
  1. select → stores transactionId, agent_id, offer_id
  2. on_select callback arrives → store accumulates contract (commitments, consideration)
  3. init → reads stored commitments from on_select, adds performance/settlements
  4. confirm → reads stored contract, changes settlement to COMPLETE
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from app.config import BAP_CALLER_URL, BAP_ID, BAP_URI, BPP_ID, BPP_URI, NETWORK_ID
from app.store import (
    get_all_callbacks, get_last_callback, get_callbacks_count,
    get_all_transactions, get_transaction, get_transaction_contract,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-api"])


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_context(action: str, transaction_id: str | None = None) -> dict:
    return {
        "networkId": NETWORK_ID,
        "action": action,
        "version": "2.0.0",
        "bapId": BAP_ID,
        "bapUri": BAP_URI,
        "bppId": BPP_ID,
        "bppUri": BPP_URI,
        "transactionId": transaction_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
    }


async def _send_to_onix(action: str, payload: dict) -> dict:
    url = f"{BAP_CALLER_URL}/{action}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            logger.info(f"→ {action} sent to {url} — HTTP {response.status_code}")
            try:
                return response.json()
            except Exception:
                return {"message": {"ack": {"status": "ACK"}}, "raw": response.text}
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error(f"ONIX unreachable for {action}: {e}")
        raise httpx.ConnectError(str(e)) from e


# ── Transaction endpoints ────────────────────────────────────

class SelectRequest(BaseModel):
    transaction_id: Optional[str] = None
    agent_id: str = "agent-summarizer-001"
    offer_id: str = "offer-summarizer-basic"
    quantity: int = 1
    buyer_name: str = "Marketplace User"


@router.post("/contracts/select")
async def select(req: SelectRequest):
    """Start a new transaction: select an agent."""
    txn_id = req.transaction_id or str(uuid.uuid4())
    ctx = _build_context("select", txn_id)
    ctx["schemaContext"] = []

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": f"contract-{txn_id[:8]}",
                "participants": [
                    {"id": "participant-buyer-001", "descriptor": {"name": req.buyer_name, "code": "buyer"}}
                ],
                "commitments": [{
                    "id": "commitment-001",
                    "descriptor": {"name": "AI Agent Service", "code": "AAS-001"},
                    "status": {"code": "DRAFT"},
                    "resources": [{
                        "id": req.agent_id,
                        "descriptor": {"name": "AI Agent", "code": req.agent_id},
                        "quantity": {"unitQuantity": req.quantity, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": req.offer_id, "resourceIds": [req.agent_id]},
                }],
            }
        },
    }

    result = await _send_to_onix("select", payload)
    return {"transactionId": txn_id, "onix_response": result}


class TxnRequest(BaseModel):
    transaction_id: str


@router.post("/contracts/init")
async def init(req: TxnRequest):
    """Continue transaction: provide fulfillment details.
    Uses stored contract data from on_select callback."""
    contract = await get_transaction_contract(req.transaction_id)
    ctx = _build_context("init", req.transaction_id)

    # Use commitments and participants from on_select if available
    commitments = contract.get("commitments", [])
    participants = contract.get("participants", [])

    # Fallback if on_select hasn't arrived yet
    if not commitments:
        logger.warning(f"init: no stored commitments for txn={req.transaction_id[:8]}, using defaults")
        commitments = [{
            "status": {"descriptor": {"code": "DRAFT"}},
            "resources": [{"id": "agent-summarizer-001", "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                           "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
            "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
        }]
    else:
        # Transform commitments for init: wrap status in descriptor
        init_commitments = []
        for c in commitments:
            ic = {**c}
            status = ic.get("status", {})
            if isinstance(status, dict) and "code" in status and "descriptor" not in status:
                ic["status"] = {"descriptor": {"code": status["code"]}}
            init_commitments.append(ic)
        commitments = init_commitments

    if not participants:
        participants = [{"id": "participant-buyer-001", "descriptor": {"name": "Marketplace User", "code": "buyer"}}]

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "commitments": commitments,
                "participants": participants,
                "performance": [{"id": "perf-001"}],
                "settlements": [{"id": "settlement-001", "status": "DRAFT"}],
            }
        },
    }

    result = await _send_to_onix("init", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


@router.post("/contracts/confirm")
async def confirm(req: TxnRequest):
    """Confirm the transaction: trigger agent execution.
    Uses stored contract data from on_select/on_init callbacks."""
    contract = await get_transaction_contract(req.transaction_id)
    ctx = _build_context("confirm", req.transaction_id)

    contract_id = contract.get("id", f"contract-{req.transaction_id[:8]}")
    commitments = contract.get("commitments", [])
    participants = contract.get("participants", [])
    performance = contract.get("performance", [{"id": "perf-001"}])
    settlements = contract.get("settlements", [{"id": "settlement-001"}])

    # Fallback
    if not commitments:
        logger.warning(f"confirm: no stored commitments for txn={req.transaction_id[:8]}, using defaults")
        commitments = [{
            "id": "commitment-001",
            "status": {"descriptor": {"code": "DRAFT"}},
            "resources": [{"id": "agent-summarizer-001", "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                           "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
            "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
        }]
    else:
        confirm_commitments = []
        for c in commitments:
            ic = {**c}
            status = ic.get("status", {})
            if isinstance(status, dict) and "code" in status and "descriptor" not in status:
                ic["status"] = {"descriptor": {"code": status["code"]}}
            confirm_commitments.append(ic)
        commitments = confirm_commitments

    if not participants:
        participants = [{"id": "participant-buyer-001", "descriptor": {"name": "Marketplace User", "code": "buyer"}}]

    # Settlements change to COMPLETE on confirm
    confirmed_settlements = [{"id": s.get("id", "settlement-001"), "status": "COMPLETE"} for s in settlements]
    if not confirmed_settlements:
        confirmed_settlements = [{"id": "settlement-001", "status": "COMPLETE"}]

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": contract_id,
                "commitments": commitments,
                "participants": participants,
                "performance": performance,
                "settlements": confirmed_settlements,
            }
        },
    }

    result = await _send_to_onix("confirm", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


@router.post("/contracts/status")
async def status(req: TxnRequest):
    """Check execution status. Uses stored commitments."""
    contract = await get_transaction_contract(req.transaction_id)
    ctx = _build_context("status", req.transaction_id)

    commitments = contract.get("commitments", [])
    if not commitments:
        commitments = [{
            "id": "commitment-001", "status": {"descriptor": {"code": "ACTIVE"}},
            "resources": [{"id": "agent-summarizer-001", "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                           "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
            "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
        }]
    else:
        status_commitments = []
        for c in commitments:
            ic = {**c}
            status_val = ic.get("status", {})
            if isinstance(status_val, dict) and "code" in status_val and "descriptor" not in status_val:
                ic["status"] = {"descriptor": {"code": "ACTIVE"}}
            status_commitments.append(ic)
        commitments = status_commitments

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": contract.get("id", f"contract-{req.transaction_id[:8]}"),
                "commitments": commitments,
            }
        },
    }

    result = await _send_to_onix("status", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


class DiscoverRequest(BaseModel):
    transaction_id: Optional[str] = None
    query: Optional[str] = None
    category: Optional[str] = None
    capabilities: Optional[List[str]] = None


@router.post("/contracts/discover")
async def discover(req: DiscoverRequest):
    """Discover available AI agents matching optional filters."""
    txn_id = req.transaction_id or str(uuid.uuid4())
    ctx = _build_context("discover", txn_id)

    # Build keywords list from all search inputs
    keywords = []
    if req.query:
        keywords.extend(req.query.split())
    if req.category:
        keywords.append(req.category)
    if req.capabilities:
        keywords.extend(req.capabilities)

    # Beckn v2 discover: use standard jsonpath and pass keywords in schemaContext
    # The BPP handler extracts keywords from context.schemaContext for DB search
    intent: dict = {
        "filters": {
            "type": "jsonpath",
            "expression": "$.catalogs[*].resources[*]",
        }
    }
    if keywords:
        ctx["schemaContext"] = keywords

    payload = {
        "context": ctx,
        "message": {"intent": intent},
    }

    result = await _send_to_onix("discover", payload)
    return {"transactionId": txn_id, "onix_response": result}


@router.post("/contracts/cancel")
async def cancel(req: TxnRequest):
    """Cancel an active transaction."""
    contract = await get_transaction_contract(req.transaction_id)
    ctx = _build_context("cancel", req.transaction_id)

    commitments = contract.get("commitments", [])
    if not commitments:
        commitments = [{"id": "commitment-001", "status": {"descriptor": {"code": "CANCELLED"}}}]
    else:
        commitments = [{**c, "status": {"descriptor": {"code": "CANCELLED"}}} for c in commitments]

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": contract.get("id", f"contract-{req.transaction_id[:8]}"),
                "commitments": commitments,
                "reason": {"descriptor": {"code": "BUYER_CANCEL", "name": "Cancelled by buyer"}},
            }
        },
    }

    result = await _send_to_onix("cancel", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


# ── Query endpoints ──────────────────────────────────────────

@router.get("/callbacks")
async def list_callbacks():
    return await get_all_callbacks()


@router.get("/callbacks/count")
async def callbacks_count():
    return {"callbacks_recibidos": await get_callbacks_count(), "status": "ok"}


@router.get("/callbacks/ultimo")
async def last_callback():
    cb = await get_last_callback()
    return cb if cb else {"error": "no callbacks yet"}


@router.get("/transactions")
async def list_transactions():
    return await get_all_transactions()


@router.get("/transactions/{txn_id}")
async def get_transaction_detail(txn_id: str):
    txn = await get_transaction(txn_id)
    return txn if txn else {"error": "transaction not found"}
