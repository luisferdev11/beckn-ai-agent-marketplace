"""
Beckn action handlers for the BPP.

Each handler corresponds to a Beckn action (select, init, confirm, status, etc.).
The handler receives the parsed request, processes it with business logic,
and returns the response payload that will be sent as the on_* callback.

Pattern (same as sandbox but with real logic):
    1. ONIX-BPP receives a signed request from the BAP
    2. ONIX validates signature + schema, forwards to us at /api/webhook/{action}
    3. We return ACK synchronously
    4. We build the on_* response and POST it to ONIX-BPP at /bpp/caller/on_{action}
    5. ONIX signs it and sends it back to the BAP
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.catalog_data import get_agent_by_id, get_offer_by_id, PROVIDER
from app.config import AGENT_URL_MAP
from app.handlers import orchestrator_client

logger = logging.getLogger(__name__)

# In-memory contract store (Iter 0 — will migrate to SQLite/Postgres)
_contracts: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def build_response_context(incoming_context: dict, action: str) -> dict:
    """
    Build the on_* callback context from the incoming context.
    Same pattern as the sandbox: copy everything, change action and timestamp.
    """
    ctx = {**incoming_context}
    ctx["action"] = f"on_{action}"
    ctx["timestamp"] = _now_iso()
    return ctx


async def handle_select(context: dict, message: dict) -> dict:
    """
    Handle select: BAP wants to select an agent.
    Returns on_select with consideration (pricing).
    """
    contract = message.get("contract", {})
    contract_id = contract.get("id", f"contract-{context['transactionId'][:8]}")

    # Extract what the BAP wants
    commitments = contract.get("commitments", [])
    participants = contract.get("participants", [])

    # Build consideration (pricing) based on the requested resources
    considerations = []
    for commitment in commitments:
        resources = commitment.get("resources", [])
        offer_ref = commitment.get("offer", {})
        offer = get_offer_by_id(offer_ref.get("id", ""))

        total_price = 0.0
        breakup = []
        for res in resources:
            agent = get_agent_by_id(res.get("id", ""))
            qty = res.get("quantity", {}).get("unitQuantity", 1)
            if agent:
                attrs = agent.get("resourceAttributes", {})
                pricing = attrs.get("pricing", {})
                unit_price = pricing.get("unitPrice", 0)
                line_total = unit_price * qty
                total_price += line_total
                breakup.append({
                    "title": f"{agent['descriptor']['name']} x{qty}",
                    "price": {"currency": "INR", "value": f"{line_total:.2f}"},
                })

        # Add taxes (18% GST)
        tax = total_price * 0.18
        breakup.append({"title": "GST (18%)", "price": {"currency": "INR", "value": f"{tax:.2f}"}})

        considerations.append({
            "id": f"consideration-{commitment.get('id', '001')}",
            "price": {"currency": "INR", "value": f"{total_price + tax:.2f}"},
            "status": {"code": "DRAFT"},
            "breakup": breakup,
        })

    # Store contract state
    _contracts[contract_id] = {
        "id": contract_id,
        "status": "DRAFT",
        "transactionId": context["transactionId"],
        "participants": participants,
        "commitments": commitments,
        "consideration": considerations,
        "created_at": _now_iso(),
    }

    logger.info(f"select: contract {contract_id} created with {len(commitments)} commitments")

    return {
        "context": build_response_context(context, "select"),
        "message": {
            "contract": {
                "id": contract_id,
                "participants": participants,
                "commitments": commitments,
                "consideration": considerations,
            }
        },
    }


async def handle_init(context: dict, message: dict) -> dict:
    """
    Handle init: BAP provides fulfillment and settlement details.
    Returns on_init confirming the terms (still DRAFT).
    """
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    # Find existing contract by transaction
    stored = None
    for c in _contracts.values():
        if c.get("transactionId") == txn_id:
            stored = c
            break

    # Merge incoming data with stored contract
    performance = contract.get("performance", [{"id": "perf-001"}])
    settlements = contract.get("settlements", [{"id": "settlement-001", "status": "DRAFT"}])

    if stored:
        stored["performance"] = performance
        stored["settlements"] = settlements
        logger.info(f"init: contract {stored['id']} updated with performance/settlements")

    response_contract = {
        "commitments": contract.get("commitments", stored.get("commitments", []) if stored else []),
        "participants": contract.get("participants", stored.get("participants", []) if stored else []),
        "performance": performance,
        "settlements": settlements,
    }

    if stored:
        response_contract["id"] = stored["id"]
        response_contract["consideration"] = stored.get("consideration", [])

    return {
        "context": build_response_context(context, "init"),
        "message": {"contract": response_contract},
    }


async def handle_confirm(context: dict, message: dict) -> dict:
    """
    Handle confirm: BAP confirms the contract.
    Marks contract ACTIVE and dispatches agent execution to the orchestrator.
    """
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = None
    for c in _contracts.values():
        if c.get("transactionId") == txn_id:
            stored = c
            break

    if stored:
        stored["status"] = "ACTIVE"
        stored["confirmed_at"] = _now_iso()
        logger.info(f"confirm: contract {stored['id']} is now ACTIVE")
        asyncio.create_task(_dispatch_to_orchestrator(stored))

    response_contract = {
        "id": contract.get("id", stored["id"] if stored else "unknown"),
        "commitments": contract.get("commitments", []),
        "participants": contract.get("participants", []),
        "performance": contract.get("performance", stored.get("performance", []) if stored else []),
        "settlements": contract.get("settlements", []),
    }

    return {
        "context": build_response_context(context, "confirm"),
        "message": {"contract": response_contract},
    }


async def _dispatch_to_orchestrator(stored: dict) -> None:
    """Fire-and-forget: call orchestrator /execute and store execution_id."""
    contract_id = stored["id"]
    commitments = stored.get("commitments", [])
    if not commitments:
        logger.warning("dispatch: no commitments in contract %s", contract_id)
        return

    resources = commitments[0].get("resources", [])
    if not resources:
        logger.warning("dispatch: no resources in contract %s", contract_id)
        return

    agent_id = resources[0].get("id", "")
    agent_url = AGENT_URL_MAP.get(agent_id, "")
    if not agent_url:
        logger.error("dispatch: no agent_url for agent_id=%s in contract %s", agent_id, contract_id)
        return

    agent_input = commitments[0].get("performanceAttributes", {}) or {}
    sla = {}
    agent_catalog = get_agent_by_id(agent_id)
    if agent_catalog:
        sla = agent_catalog.get("resourceAttributes", {}).get("sla", {})

    timeout_ms = 30000
    max_latency = sla.get("maxLatency", "PT30S")
    if max_latency.startswith("PT") and max_latency.endswith("S"):
        try:
            timeout_ms = int(float(max_latency[2:-1]) * 1000)
        except ValueError:
            pass

    try:
        ack = await orchestrator_client.start_execution({
            "contract_id": contract_id,
            "agent_id": agent_id,
            "agent_url": agent_url,
            "input": agent_input,
            "timeout_ms": timeout_ms,
        })
        stored["execution_id"] = ack.get("execution_id")
        logger.info("dispatch: contract %s → execution %s", contract_id, stored["execution_id"])
    except Exception as exc:
        logger.error("dispatch: failed to start execution for contract %s: %s", contract_id, exc)


async def handle_status(context: dict, message: dict) -> dict:
    """
    Handle status: BAP asks for execution status.
    Polls the orchestrator for real execution state.
    """
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = None
    for c in _contracts.values():
        if c.get("transactionId") == txn_id:
            stored = c
            break

    # Determine execution status from orchestrator
    exec_status = "PENDING"
    short_desc = "Execution pending"

    execution_id = stored.get("execution_id") if stored else None
    if execution_id:
        try:
            exec_data = await orchestrator_client.get_execution(execution_id)
            exec_status = exec_data.get("status", "PENDING")
            result = exec_data.get("result") or {}
            error = exec_data.get("error")
            if exec_status == "COMPLETED":
                short_desc = result.get("review") or result.get("summary") or str(result)
            elif exec_status == "FAILED":
                short_desc = error or "Agent execution failed"
            else:
                short_desc = f"Execution {exec_status.lower()}"
        except Exception as exc:
            logger.error("status: failed to poll orchestrator for execution %s: %s", execution_id, exc)
            short_desc = "Could not retrieve execution status"

    # TODO: add performanceAttributes once schema is hosted at a public URL.
    # ONIX fetches the @context URL to validate extended schemas — until
    # schemas/ai-agents-v1.json is published, the result lives in shortDesc.
    performance = [{
        "id": "perf-001",
        "status": {
            "code": exec_status,
            "name": exec_status.replace("_", " ").title(),
            "shortDesc": short_desc[:500] if short_desc else "",
        },
    }]

    commitments = stored.get("commitments", []) if stored else contract.get("commitments", [])
    if not commitments:
        commitments = [{"id": "commitment-001", "status": {"code": "ACTIVE"},
                        "resources": [{"id": "agent-summarizer-001",
                                       "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                                       "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
                        "offer": {"id": "offer-summarizer-basic", "resourceIds": ["agent-summarizer-001"]}}]

    response_contract = {
        "id": contract.get("id", stored["id"] if stored else "unknown"),
        "commitments": commitments,
        "performance": performance,
    }

    return {
        "context": build_response_context(context, "status"),
        "message": {"contract": response_contract},
    }


async def handle_cancel(context: dict, message: dict) -> dict:
    """Handle cancel: BAP cancels the contract."""
    contract = message.get("contract", {})
    return {
        "context": build_response_context(context, "cancel"),
        "message": {"contract": {**contract, "status": {"code": "CANCELLED"}}},
    }


async def handle_rating(context: dict, message: dict) -> dict:
    """Handle rating: BAP rates the agent."""
    ratings = message.get("ratings", [])
    logger.info(f"rating received: {ratings}")
    return {
        "context": build_response_context(context, "rating"),
        "message": {"ratings": ratings},
    }


async def handle_support(context: dict, message: dict) -> dict:
    """Handle support: returns contact info."""
    return {
        "context": build_response_context(context, "support"),
        "message": {
            "support": {
                "email": "support@ai-marketplace.example.com",
                "phone": "+91-1234567890",
            }
        },
    }


# Action dispatcher
ACTION_HANDLERS = {
    "select": handle_select,
    "init": handle_init,
    "confirm": handle_confirm,
    "status": handle_status,
    "cancel": handle_cancel,
    "rating": handle_rating,
    "support": handle_support,
}
