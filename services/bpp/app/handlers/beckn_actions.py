"""
Beckn action handlers for the BPP — PostgreSQL backed.

Each handler corresponds to a Beckn action (select, init, confirm, status, etc.).
The handler receives the parsed request, processes it with business logic,
and returns the response payload that will be sent as the on_* callback.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.config import AGENT_URL_MAP
from app.db import repository as repo
from app.handlers import orchestrator_client
from app.routes.provider_api import _agent_to_beckn_resource

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def build_response_context(incoming_context: dict, action: str) -> dict:
    ctx = {**incoming_context}
    ctx["action"] = f"on_{action}"
    ctx["timestamp"] = _now_iso()
    return ctx


def _parse_jsonb(val):
    """Safely parse a JSONB value that might be a string or already a dict/list."""
    if isinstance(val, str):
        return json.loads(val)
    return val


async def handle_discover(context: dict, message: dict) -> dict:
    """
    Handle discover: search agents by keywords from the intent.
    Searches capabilities, skills, agent_name, and description.
    """
    intent = message.get("intent", {})
    keywords = []

    # Keywords passed via context.schemaContext by our BAP
    schema_context = context.get("schemaContext", [])
    if isinstance(schema_context, list):
        keywords.extend([k for k in schema_context if isinstance(k, str)])

    if keywords:
        agents = await repo.search_agents(keywords)
    else:
        agents = await repo.list_agents()
        agents = [a for a in agents if a["status"] == "active"]

    resources = [_agent_to_beckn_resource(a) for a in agents]

    if agents:
        provider_org = agents[0].get("provider_org", {})
        if isinstance(provider_org, str):
            provider_org = json.loads(provider_org)
        provider_block = {
            "id": str(agents[0]["provider_id"]),
            "descriptor": {"name": provider_org.get("name", "Provider")},
        }
    else:
        provider_block = {"id": "none", "descriptor": {"name": "No providers"}}

    catalog = {
        "id": "catalog-discover-results",
        "descriptor": {
            "name": "AI Agent Catalog",
            "shortDesc": f"Found {len(resources)} agents",
        },
        "provider": provider_block,
        "resources": resources,
        "offers": [
            {
                "id": f"offer-agent-{a['id']}",
                "descriptor": {
                    "name": (json.loads(a['agent_name']) if isinstance(a['agent_name'], str) else a['agent_name']).get('en', 'Agent'),
                },
                "resourceIds": [str(a["id"])],
            }
            for a in agents
        ],
    }

    logger.info("discover: returning %d agents (keywords: %s)", len(resources), keywords)
    return {
        "context": build_response_context(context, "discover"),
        "message": {"catalogs": [catalog]},
    }


async def handle_select(context: dict, message: dict) -> dict:
    """Handle select: BAP wants to select an agent. Returns pricing."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]
    contract_code = contract.get("id", f"contract-{txn_id[:8]}")
    commitments = contract.get("commitments", [])
    participants = contract.get("participants", [])

    considerations = []
    for commitment in commitments:
        resources = commitment.get("resources", [])
        total_price = 0.0
        breakup = []

        for res in resources:
            agent_id_str = res.get("id", "")
            try:
                agent_id_int = int(agent_id_str)
                agent = await repo.get_agent_by_id(agent_id_int)
            except (ValueError, TypeError):
                agent = None

            qty = res.get("quantity", {}).get("unitQuantity", 1)
            if agent:
                pricing = _parse_jsonb(agent.get("pricing_model", {}))
                unit_price = pricing.get("value", pricing.get("unitPrice", 0))
                line_total = float(unit_price) * qty
                total_price += line_total
                name = _parse_jsonb(agent.get("agent_name", {}))
                label = name.get("en", "Agent") if isinstance(name, dict) else str(name)
                breakup.append({
                    "title": f"{label} x{qty}",
                    "price": {"currency": pricing.get("currency", "INR"), "value": f"{line_total:.2f}"},
                })

        tax = total_price * 0.18
        breakup.append({"title": "GST (18%)", "price": {"currency": "INR", "value": f"{tax:.2f}"}})

        considerations.append({
            "id": f"consideration-{commitment.get('id', '001')}",
            "price": {"currency": "INR", "value": f"{total_price + tax:.2f}"},
            "status": {"code": "DRAFT"},
            "breakup": breakup,
        })

    await repo.create_contract(
        contract_code=contract_code,
        transaction_id=txn_id,
        commitments=commitments,
        consideration=considerations,
        participants=participants,
        status="DRAFT",
        bap_id=context.get("bapId"),
        bpp_id=context.get("bppId"),
        total_amount=sum(float(c["price"]["value"]) for c in considerations) if considerations else None,
    )

    logger.info(f"select: contract {contract_code} created with {len(commitments)} commitments")

    return {
        "context": build_response_context(context, "select"),
        "message": {
            "contract": {
                "id": contract_code,
                "participants": participants,
                "commitments": commitments,
                "consideration": considerations,
            }
        },
    }


async def handle_init(context: dict, message: dict) -> dict:
    """Handle init: BAP provides fulfillment and settlement details."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = await repo.get_contract_by_txn(txn_id)

    performance = contract.get("performance", [{"id": "perf-001"}])
    settlements = contract.get("settlements", [{"id": "settlement-001", "status": "DRAFT"}])

    if stored:
        await repo.update_contract(txn_id,
            performance=performance,
            settlements=settlements,
            initialized_at=datetime.now(timezone.utc),
        )
        logger.info(f"init: contract updated with performance/settlements [txn={txn_id[:8]}]")

    stored_commitments = _parse_jsonb(stored["commitments"]) if stored else []
    stored_participants = _parse_jsonb(stored["participants"]) if stored else []
    stored_consideration = _parse_jsonb(stored["consideration"]) if stored else []

    response_contract = {
        "commitments": contract.get("commitments", stored_commitments),
        "participants": contract.get("participants", stored_participants),
        "performance": performance,
        "settlements": settlements,
    }

    if stored:
        response_contract["id"] = stored["contract_code"]
        response_contract["consideration"] = stored_consideration

    return {
        "context": build_response_context(context, "init"),
        "message": {"contract": response_contract},
    }


async def handle_confirm(context: dict, message: dict) -> dict:
    """Handle confirm: BAP confirms. Mark ACTIVE and dispatch to orchestrator."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = await repo.get_contract_by_txn(txn_id)

    # Update contract with confirm data (commitments may contain the prompt)
    confirm_commitments = contract.get("commitments", [])
    if stored:
        updates = {
            "status": "ACTIVE",
            "confirmed_at": datetime.now(timezone.utc),
        }
        if confirm_commitments:
            updates["commitments"] = confirm_commitments
        await repo.update_contract(txn_id, **updates)
        # Re-read stored to get updated commitments
        stored = await repo.get_contract_by_txn(txn_id)
        logger.info(f"confirm: contract ACTIVE [txn={txn_id[:8]}]")
        asyncio.create_task(_dispatch_to_orchestrator(txn_id, stored))

    response_contract = {
        "id": contract.get("id", stored["contract_code"] if stored else "unknown"),
        "commitments": contract.get("commitments", []),
        "participants": contract.get("participants", []),
        "performance": contract.get("performance", _parse_jsonb(stored["performance"]) if stored else []),
        "settlements": contract.get("settlements", []),
    }

    return {
        "context": build_response_context(context, "confirm"),
        "message": {"contract": response_contract},
    }


async def _dispatch_to_orchestrator(txn_id: str, stored: dict) -> None:
    """Fire-and-forget: call orchestrator /execute and store execution_id."""
    commitments = _parse_jsonb(stored.get("commitments", []))
    if not commitments:
        return

    resources = commitments[0].get("resources", [])
    if not resources:
        return

    agent_id_str = resources[0].get("id", "")

    # Try to resolve agent URL from DB or fallback to config
    agent_url = AGENT_URL_MAP.get(agent_id_str, "http://agents:3004")

    # Extract prompt from multiple possible locations in the commitment
    agent_input = commitments[0].get("performanceAttributes", {}) or {}
    # Also check resource descriptor longDesc (used for text prompts)
    resources = commitments[0].get("resources", [])
    if resources and not agent_input:
        desc = resources[0].get("descriptor", {})
        prompt_text = desc.get("longDesc", "") or desc.get("shortDesc", "")
        if prompt_text:
            agent_input = {"prompt": prompt_text}
    sla = {}
    try:
        agent_id_int = int(agent_id_str)
        agent = await repo.get_agent_by_id(agent_id_int)
        if agent:
            sla = _parse_jsonb(agent.get("sla", {}))
            agent_url = agent.get("access_point_url") or agent_url
    except (ValueError, TypeError):
        pass

    timeout_ms = int(sla.get("maxLatencyMs", 30000))

    try:
        ack = await orchestrator_client.start_execution({
            "contract_id": stored["contract_code"],
            "agent_id": agent_id_str,
            "agent_url": agent_url,
            "input": agent_input,
            "timeout_ms": timeout_ms,
        })
        execution_id = ack.get("execution_id")
        await repo.update_contract(txn_id, execution_id=execution_id)
        logger.info("dispatch: txn %s → execution %s", txn_id[:8], execution_id)
    except Exception as exc:
        logger.error("dispatch: failed for txn %s: %s", txn_id[:8], exc)


async def handle_status(context: dict, message: dict) -> dict:
    """Handle status: polls orchestrator for execution state."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = await repo.get_contract_by_txn(txn_id)

    exec_status = "PENDING"
    short_desc = "Execution pending"
    result: dict = {}
    metadata: dict = {}

    execution_id = stored.get("execution_id") if stored else None
    if execution_id:
        try:
            exec_data = await orchestrator_client.get_execution(execution_id)
            exec_status = exec_data.get("status", "PENDING")
            result = exec_data.get("result") or {}
            metadata = exec_data.get("metadata") or {}
            error = exec_data.get("error")
            if exec_status == "COMPLETED":
                short_desc = result.get("review") or result.get("summary") or str(result)
                await repo.update_contract(txn_id,
                    status="COMPLETED",
                    completed_at=datetime.now(timezone.utc),
                )
            elif exec_status == "FAILED":
                short_desc = error or "Agent execution failed"
                await repo.update_contract(txn_id, status="FAILED")
            else:
                short_desc = f"Execution {exec_status.lower()}"
        except Exception as exc:
            logger.error("status: failed to poll orchestrator: %s", exc)
            short_desc = "Could not retrieve execution status"

    schema_url = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/execution-result-v1.json"
    performance = [{
        "id": "perf-001",
        "status": {
            "code": exec_status,
            "name": exec_status.replace("_", " ").title(),
            "shortDesc": short_desc[:500] if short_desc else "",
        },
        "performanceAttributes": {
            "@context": schema_url,
            "@type": "beckn:AgentExecution",
            "startedAt": metadata.get("started_at") or _now_iso(),
            "completedAt": metadata.get("completed_at") or _now_iso(),
            "latencyMs": metadata.get("latency_ms") or 0,
            "tokensUsed": metadata.get("tokens_used") or {"input": 0, "output": 0, "total": 0},
            "model": metadata.get("model") or "unknown",
            "result": result,
            "status": exec_status,
        },
    }]

    stored_commitments = _parse_jsonb(stored["commitments"]) if stored else []
    commitments = stored_commitments or contract.get("commitments", [])
    if not commitments:
        commitments = [{"id": "commitment-001", "status": {"code": "ACTIVE"},
                        "resources": [{"id": "1", "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                                       "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
                        "offer": {"id": "offer-agent-1", "resourceIds": ["1"]}}]

    return {
        "context": build_response_context(context, "status"),
        "message": {
            "contract": {
                "id": contract.get("id", stored["contract_code"] if stored else "unknown"),
                "commitments": commitments,
                "performance": performance,
            }
        },
    }


async def handle_cancel(context: dict, message: dict) -> dict:
    txn_id = context["transactionId"]
    contract = message.get("contract", {})
    await repo.update_contract(txn_id, status="CANCELLED")
    return {
        "context": build_response_context(context, "cancel"),
        "message": {"contract": {**contract, "status": {"code": "CANCELLED"}}},
    }


async def handle_rating(context: dict, message: dict) -> dict:
    ratings = message.get("ratings", [])
    logger.info(f"rating received: {ratings}")
    return {
        "context": build_response_context(context, "rating"),
        "message": {"ratings": ratings},
    }


async def handle_support(context: dict, message: dict) -> dict:
    return {
        "context": build_response_context(context, "support"),
        "message": {
            "support": {
                "email": "support@ai-marketplace.example.com",
                "phone": "+91-1234567890",
            }
        },
    }


ACTION_HANDLERS = {
    "discover": handle_discover,
    "select": handle_select,
    "init": handle_init,
    "confirm": handle_confirm,
    "status": handle_status,
    "cancel": handle_cancel,
    "rating": handle_rating,
    "support": handle_support,
}
