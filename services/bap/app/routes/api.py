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
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from app.config import BAP_CALLER_URL, BAP_ID, BAP_URI, BPP_ID, BPP_URI, NETWORK_ID
from app.store import (
    get_all_callbacks, get_last_callback, get_callbacks_count,
    get_all_transactions, get_transaction, get_transaction_contract,
    set_transaction_target, get_transaction_target,
    create_draft_contract, contract_exists,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bap-api"])


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _build_context(
    action: str,
    transaction_id: str | None = None,
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
        "transactionId": transaction_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
    }


def _resolve_bpp_target(req_bpp_id: str | None, req_bpp_uri: str | None, txn_id: str) -> tuple[str | None, str | None]:
    """Pick the BPP target: explicit override > stored from select > config default."""
    if req_bpp_id and req_bpp_uri:
        return req_bpp_id, req_bpp_uri
    target = get_transaction_target(txn_id)
    return target.get("bpp_id") or req_bpp_id, target.get("bpp_uri") or req_bpp_uri


async def _require_known_transaction(txn_id: str, action: str) -> None:
    """Reject actions on transactions that never went through select.

    Without this guard, the BAP would forward the request to the BPP and the
    resulting on_* callback would (used to) materialize a phantom contract row.
    See issue #12.
    """
    if not await contract_exists(txn_id):
        logger.warning(f"rejected {action} for unknown txn={txn_id[:8]} — no prior select")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "transaction_not_found",
                "message": f"No contract exists for transaction_id={txn_id}. "
                           f"You must call /api/contracts/select first.",
                "transaction_id": txn_id,
            },
        )


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
    # Optional overrides — used after a federated discover to pick a specific BPP.
    bpp_id: Optional[str] = None
    bpp_uri: Optional[str] = None


@router.post("/contracts/select")
async def select(req: SelectRequest):
    """Start a new transaction: select an agent."""
    txn_id = req.transaction_id or str(uuid.uuid4())
    ctx = _build_context("select", txn_id, req.bpp_id, req.bpp_uri)
    ctx["schemaContext"] = []
    # Remember which BPP this txn targets so init/confirm/status reuse it.
    set_transaction_target(txn_id, ctx["bppId"], ctx["bppUri"])

    contract_code = f"contract-{txn_id[:8]}"
    participants = [
        {"id": "participant-buyer-001", "descriptor": {"name": req.buyer_name, "code": "buyer"}}
    ]
    commitments = [{
        "id": "commitment-001",
        "descriptor": {"name": "AI Agent Service", "code": "AAS-001"},
        "status": {"code": "DRAFT"},
        "resources": [{
            "id": req.agent_id,
            "descriptor": {"name": "AI Agent", "code": req.agent_id},
            "quantity": {"unitQuantity": req.quantity, "unitCode": "UNIT"},
        }],
        "offer": {"id": req.offer_id, "resourceIds": [req.agent_id]},
    }]

    # Materialize the contract in DRAFT before talking to the network. This
    # is the only path that creates rows in `contracts` — callbacks never do.
    # Makes the invariant "row exists ⇔ legitimate select happened" true by
    # construction, and lets later endpoints fail fast with 404. See issue #12.
    await create_draft_contract(txn_id, contract_code, commitments, participants)

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": contract_code,
                "participants": participants,
                "commitments": commitments,
            }
        },
    }

    result = await _send_to_onix("select", payload)
    return {"transactionId": txn_id, "onix_response": result}


class TxnRequest(BaseModel):
    transaction_id: str
    bpp_id: Optional[str] = None
    bpp_uri: Optional[str] = None


class ConfirmRequest(TxnRequest):
    # Optional agent input passed through to the BPP; embedded in the
    # commitment's performanceAttributes so the orchestrator can dispatch
    # it to the agent's /task endpoint.
    agent_id: Optional[str] = None
    agent_input: Optional[dict] = None


@router.post("/contracts/init")
async def init(req: TxnRequest):
    """Continue transaction: provide fulfillment details.
    Uses stored contract data from on_select callback."""
    await _require_known_transaction(req.transaction_id, "init")
    contract = await get_transaction_contract(req.transaction_id)
    bpp_id, bpp_uri = _resolve_bpp_target(req.bpp_id, req.bpp_uri, req.transaction_id)
    ctx = _build_context("init", req.transaction_id, bpp_id, bpp_uri)

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
async def confirm(req: ConfirmRequest):
    """Confirm the transaction: trigger agent execution.
    Uses stored contract data from on_select/on_init callbacks."""
    await _require_known_transaction(req.transaction_id, "confirm")
    contract = await get_transaction_contract(req.transaction_id)
    bpp_id, bpp_uri = _resolve_bpp_target(req.bpp_id, req.bpp_uri, req.transaction_id)
    ctx = _build_context("confirm", req.transaction_id, bpp_id, bpp_uri)

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
            # Embed agent_input where the BPP/orchestrator expects to read it.
            if req.agent_input:
                ic["performanceAttributes"] = {
                    **(ic.get("performanceAttributes") or {}),
                    **req.agent_input,
                }
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
    await _require_known_transaction(req.transaction_id, "status")
    contract = await get_transaction_contract(req.transaction_id)
    bpp_id, bpp_uri = _resolve_bpp_target(req.bpp_id, req.bpp_uri, req.transaction_id)
    ctx = _build_context("status", req.transaction_id, bpp_id, bpp_uri)

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


class DiscoverFilters(BaseModel):
    """Structured filter shape accepted by the CDS (Pieza 2).

    The CDS combines these with the textSearch via SQL WHERE (hard
    filter) then ranks the surviving candidates by semantic similarity.
    Empty/omitted fields mean "no constraint".
    """
    jurisdiction: Optional[str] = None
    languages: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    currency: Optional[str] = None
    max_price_value: Optional[float] = None
    max_latency_ms: Optional[int] = None


class DiscoverRequest(BaseModel):
    """Body for ``POST /api/contracts/discover``.

    The cleanest path is ``intent_text``: a curated natural-language
    prompt that goes straight to ``intent.textSearch`` and gets embedded
    by the CDS for semantic ranking. This is what the input-sanitiser
    ("espantapendejos") and the planner team should use.

    The legacy ``query``/``category``/``capabilities`` fields stay for
    backwards compatibility — they get joined into ``context.schemaContext``
    (the CDS treats schemaContext as a fallback when textSearch is empty).
    """
    transaction_id: Optional[str] = None

    # Preferred: curated prompt → intent.textSearch
    intent_text: Optional[str] = None

    # Optional structured filters → intent.filters
    filters: Optional[DiscoverFilters] = None
    limit: Optional[int] = None

    # Legacy keyword inputs — kept for backwards compatibility
    query: Optional[str] = None
    category: Optional[str] = None
    capabilities: Optional[List[str]] = None


@router.post("/contracts/discover")
async def discover(req: DiscoverRequest):
    """Discover agents in the network.

    Two inputs combine:
      - ``intent_text``: natural-language prompt for semantic search.
      - ``filters``: structured hard constraints (jurisdiction, languages, ...).

    Legacy ``query/category/capabilities`` keywords still work and route to
    ``context.schemaContext`` for backwards-compat; CDS falls back to that
    only when ``intent_text`` is empty.
    """
    txn_id = req.transaction_id or str(uuid.uuid4())
    ctx = _build_context("discover", txn_id)

    intent: dict = {}
    if req.intent_text and req.intent_text.strip():
        intent["textSearch"] = req.intent_text.strip()

    # NOTE on ``intent.filters`` and ``intent.limit``:
    # The Beckn v2 OpenAPI spec (validated by ONIX) declares
    # ``intent`` with ``additionalProperties: false`` and only allows
    # ``textSearch``, ``filters`` (as JSONPath {type, expression}),
    # ``spatial``, ``mediaSearch``. Our structured DiscoverFilters and
    # ``limit`` field do NOT fit that shape — ONIX returns NACK with
    # "property X is unsupported". To stay schema-compliant on the
    # BAP→ONIX→CDS path, we carry structured hints in
    # ``context.schemaContext`` (an array slot the spec leaves to the
    # network to interpret). The CDS understands this convention via
    # ``app.discover.models.from_envelope``. Proper JSONPath translation
    # is roadmap.
    hints: list[str] = []
    if req.filters:
        filters_dict = req.filters.model_dump(exclude_none=True)
        for key, value in filters_dict.items():
            if isinstance(value, list):
                for item in value:
                    hints.append(f"filter:{key}={item}")
            else:
                hints.append(f"filter:{key}={value}")
    if req.limit is not None:
        hints.append(f"limit={req.limit}")

    # Legacy keyword fallback — collected into schemaContext so the CDS can
    # still surface them when intent_text is missing.
    keywords: list[str] = []
    if req.query:
        keywords.extend(req.query.split())
    if req.category:
        keywords.append(req.category)
    if req.capabilities:
        keywords.extend(req.capabilities)
    if keywords or hints:
        ctx["schemaContext"] = keywords + hints

    payload = {
        "context": ctx,
        "message": {"intent": intent},
    }

    result = await _send_to_onix("discover", payload)
    return {"transactionId": txn_id, "onix_response": result}


@router.post("/contracts/cancel")
async def cancel(req: TxnRequest):
    """Cancel an active transaction."""
    await _require_known_transaction(req.transaction_id, "cancel")
    contract = await get_transaction_contract(req.transaction_id)
    bpp_id, bpp_uri = _resolve_bpp_target(req.bpp_id, req.bpp_uri, req.transaction_id)
    ctx = _build_context("cancel", req.transaction_id, bpp_id, bpp_uri)

    # Beckn v2 schema:
    #   - Commitment.status.code enum: {DRAFT, ACTIVE, CLOSED}
    #   - Contract.status.code enum:   {DRAFT, ACTIVE, CANCELLED, COMPLETE}
    # Contract has additionalProperties:false so a free-form `reason`
    # cannot ride here; if we need to surface a reason on the wire we'd
    # need to wrap it in a JSON-LD `contractAttributes` object — not
    # done yet because no consumer needs it.
    commitments = contract.get("commitments", [])
    if not commitments:
        commitments = [{"id": "commitment-001", "status": {"descriptor": {"code": "CLOSED"}}}]
    else:
        commitments = [{**c, "status": {"descriptor": {"code": "CLOSED"}}} for c in commitments]

    payload = {
        "context": ctx,
        "message": {
            "contract": {
                "id": contract.get("id", f"contract-{req.transaction_id[:8]}"),
                "commitments": commitments,
                # Contract.status is a Descriptor directly (no nested "descriptor" key),
                # asymmetric to Commitment.status which is {descriptor: Descriptor}.
                "status": {"code": "CANCELLED"},
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
async def callbacks_count(transaction_id: str | None = None):
    return {"callbacks_recibidos": await get_callbacks_count(transaction_id), "status": "ok"}


@router.get("/callbacks/ultimo")
async def last_callback(transaction_id: str | None = None):
    cb = await get_last_callback(transaction_id)
    return cb if cb else {"error": "no callbacks yet"}


@router.get("/transactions")
async def list_transactions():
    return await get_all_transactions()


@router.get("/transactions/{txn_id}")
async def get_transaction_detail(txn_id: str):
    txn = await get_transaction(txn_id)
    return txn if txn else {"error": "transaction not found"}
