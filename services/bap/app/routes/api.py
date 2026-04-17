"""
BAP API routes — the active side that originates Beckn transactions.

These endpoints are called by the frontend (or scripts/tests) to trigger
Beckn actions. The BAP builds the Beckn payload and POSTs it to
ONIX-BAP at /bap/caller/{action}.

Flow: Frontend → BAP API → ONIX-BAP (sign + route) → ONIX-BPP → BPP
"""

import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.config import BAP_CALLER_URL, BAP_ID, BAP_URI, BPP_ID, BPP_URI, NETWORK_ID
from app.store import get_all_callbacks, get_last_callback, get_callbacks_count, get_all_transactions, get_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-api"])


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_context(action: str, transaction_id: str | None = None) -> dict:
    """Build a Beckn context for an outgoing action."""
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
    """Send a Beckn action to ONIX-BAP caller."""
    url = f"{BAP_CALLER_URL}/{action}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        logger.info(f"→ {action} sent to {url} — HTTP {response.status_code}")
        return response.json()


# ── Transaction endpoints ────────────────────────────────────

class SelectRequest(BaseModel):
    transaction_id: Optional[str] = None
    agent_id: str = "agent-summarizer-001"
    offer_id: str = "offer-summarizer-basic"
    quantity: int = 1


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
                    {"id": "participant-buyer-001", "descriptor": {"name": "Marketplace User", "code": "buyer"}}
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


class InitRequest(BaseModel):
    transaction_id: str


@router.post("/contracts/init")
async def init(req: InitRequest):
    """Continue transaction: provide fulfillment details."""
    ctx = _build_context("init", req.transaction_id)

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "commitments": [{
                    "status": {"descriptor": {"code": "DRAFT"}},
                    "resources": [{
                        "id": "agent-summarizer-001",
                        "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                        "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
                }],
                "participants": [
                    {"id": "participant-buyer-001", "descriptor": {"name": "Marketplace User", "code": "buyer"}}
                ],
                "performance": [{"id": "perf-001"}],
                "settlements": [{"id": "settlement-001", "status": "DRAFT"}],
            }
        },
    }

    result = await _send_to_onix("init", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


class ConfirmRequest(BaseModel):
    transaction_id: str


@router.post("/contracts/confirm")
async def confirm(req: ConfirmRequest):
    """Confirm the transaction: trigger agent execution."""
    ctx = _build_context("confirm", req.transaction_id)

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": f"contract-{req.transaction_id[:8]}",
                "commitments": [{
                    "id": "commitment-001",
                    "status": {"descriptor": {"code": "DRAFT"}},
                    "resources": [{
                        "id": "agent-summarizer-001",
                        "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                        "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
                }],
                "participants": [
                    {"id": "participant-buyer-001", "descriptor": {"name": "Marketplace User", "code": "buyer"}}
                ],
                "performance": [{"id": "perf-001"}],
                "settlements": [{"id": "settlement-001", "status": "COMPLETE"}],
            }
        },
    }

    result = await _send_to_onix("confirm", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


class StatusRequest(BaseModel):
    transaction_id: str


@router.post("/contracts/status")
async def status(req: StatusRequest):
    """Check execution status."""
    ctx = _build_context("status", req.transaction_id)
    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": f"contract-{req.transaction_id[:8]}",
                "commitments": [{
                    "id": "commitment-001",
                    "status": {"descriptor": {"code": "ACTIVE"}},
                    "resources": [{
                        "id": "agent-summarizer-001",
                        "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                        "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]},
                }],
            }
        },
    }
    result = await _send_to_onix("status", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}


# ── Query endpoints ──────────────────────────────────────────

@router.get("/callbacks")
async def list_callbacks():
    """List all callbacks received."""
    return get_all_callbacks()


@router.get("/callbacks/count")
async def callbacks_count():
    """Return callback count."""
    return {"callbacks_recibidos": get_callbacks_count(), "status": "ok"}


@router.get("/callbacks/ultimo")
async def last_callback():
    """Return the last callback received."""
    cb = get_last_callback()
    return cb if cb else {"error": "no callbacks yet"}


@router.get("/transactions")
async def list_transactions():
    """List all transactions."""
    return get_all_transactions()


@router.get("/transactions/{txn_id}")
async def get_transaction_detail(txn_id: str):
    """Get details of a specific transaction."""
    txn = get_transaction(txn_id)
    return txn if txn else {"error": "transaction not found"}
