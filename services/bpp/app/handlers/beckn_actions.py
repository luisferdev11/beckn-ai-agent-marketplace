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

import httpx

from app.config import BPP_ID, BPP_URI, CDS_BASE_URL
from app.db import repository as repo
from app.handlers import orchestrator_client
from app.routes.provider_api import _agent_to_beckn_resource

CDS_INGEST_TIMEOUT_SECONDS = 3.0

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def build_response_context(incoming_context: dict, action: str) -> dict:
    """
    Build the on_* callback context from the incoming context.

    Self-identify: when the Discovery Service fan-outs a discover, every BPP
    receives it with the BAP's default bppId. Each BPP MUST overwrite
    bppId/bppUri here with its own config so ONIX-BPP-X signs with its
    own keypair and the BAP attributes the catalog correctly.
    """
    ctx = {**incoming_context}
    ctx["action"] = f"on_{action}"
    ctx["timestamp"] = _now_iso()
    ctx["bppId"] = BPP_ID
    ctx["bppUri"] = BPP_URI
    return ctx


# Beckn v2 error code for missing transactional continuity.
# Returned by on_init/on_confirm/on_status/on_cancel when the txn was never
# acknowledged on this BPP (no prior on_select stored). See issue #14.
TXN_NOT_FOUND_CODE = "30002"
TXN_NOT_FOUND_MESSAGE = "Transaction not found"

# Beckn v2 error code returned by on_select when at least one requested
# resource does not match any agent in this BPP's catalog. See issue #15.
UNKNOWN_AGENT_CODE = "30001"


def _txn_not_found_response(context: dict, action: str) -> dict:
    """
    Build an on_<action> envelope that signals the txn is unknown to this BPP.

    The envelope keeps a valid Beckn context (with the action flipped to on_*)
    and adds a top-level `error` field per Beckn v2. No `message` is included
    because there is no contract state to echo back — this protects against
    phantom-row writes from cross-BPP misrouting.
    """
    return {
        "context": build_response_context(context, action),
        "error": {
            "code": TXN_NOT_FOUND_CODE,
            "message": TXN_NOT_FOUND_MESSAGE,
        },
    }


def _unknown_agent_response(context: dict, agent_id: str) -> dict:
    """
    Build an on_select envelope that rejects a select carrying a resource id
    we cannot resolve in our catalog. Mirrors `_txn_not_found_response`: only
    context + error, no message — so the BAP sees a clear failure rather
    than a price=0 contract.
    """
    return {
        "context": build_response_context(context, "select"),
        "error": {
            "code": UNKNOWN_AGENT_CODE,
            "message": f"Agent not found: {agent_id}",
        },
    }


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
                "resourceIds": [a["beckn_id"] or str(a["id"])],
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

    # All-or-nothing pre-validation: a single unresolvable resource fails the
    # whole select with error 30001. "Unresolvable" means the agent does not
    # exist OR has status != 'active' (inactive/deprecated). From the user's
    # point of view both cases are equivalent — the requested resource cannot
    # be fulfilled. Without this guard, missing or inactive agents silently
    # dropped out of the pricing loop and the BAP ended up with a DRAFT
    # contract priced at 0.00 + 18% GST = 0.00. See issue #15.
    resolved_agents: dict[str, dict] = {}
    for commitment in commitments:
        for res in commitment.get("resources", []):
            agent_beckn_id = res.get("id", "")
            if agent_beckn_id in resolved_agents:
                continue
            agent = await repo.get_agent_by_beckn_id(agent_beckn_id)
            if not agent or agent.get("status") != "active":
                reason = "unknown" if not agent else f"status={agent.get('status')}"
                logger.warning(
                    f"select: rejecting agent {agent_beckn_id} ({reason}) [txn={txn_id[:8]}]"
                )
                return _unknown_agent_response(context, agent_beckn_id)
            resolved_agents[agent_beckn_id] = agent

    considerations = []
    for commitment in commitments:
        resources = commitment.get("resources", [])
        total_price = 0.0
        breakup = []

        for res in resources:
            agent_beckn_id = res.get("id", "")
            agent = resolved_agents[agent_beckn_id]

            qty = res.get("quantity", {}).get("unitQuantity", 1)
            if agent:
                pricing = _parse_jsonb(agent.get("pricing_model", {}))
                unit_price = pricing.get("value", pricing.get("unitPrice", 0))
                line_total = float(unit_price) * qty
                total_price += line_total
                label = agent.get("label") or "Agent"
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

    # Resolve agent_id from the first commitment resource
    agent_db_id = None
    if commitments:
        first_res = commitments[0].get("resources", [{}])[0]
        agent = await repo.get_agent_by_beckn_id(first_res.get("id", ""))
        if agent:
            agent_db_id = agent["id"]

    await repo.create_contract(
        contract_code=contract_code,
        transaction_id=txn_id,
        commitments=commitments,
        consideration=considerations,
        participants=participants,
        status="DRAFT",
        agent_id=agent_db_id,
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
    if not stored:
        logger.warning(f"init: txn unknown to this BPP, rejecting [txn={txn_id[:8]}]")
        return _txn_not_found_response(context, "init")

    performance = contract.get("performance", [{"id": "perf-001"}])
    settlements = contract.get("settlements", [{"id": "settlement-001", "status": "DRAFT"}])

    await repo.update_contract(txn_id,
        performance=performance,
        settlements=settlements,
        initialized_at=datetime.now(timezone.utc),
    )
    logger.info(f"init: contract updated with performance/settlements [txn={txn_id[:8]}]")

    stored_commitments = _parse_jsonb(stored["commitments"])
    stored_participants = _parse_jsonb(stored["participants"])
    stored_consideration = _parse_jsonb(stored["consideration"])

    response_contract = {
        "id": stored["contract_code"],
        "commitments": contract.get("commitments", stored_commitments),
        "participants": contract.get("participants", stored_participants),
        "consideration": stored_consideration,
        "performance": performance,
        "settlements": settlements,
    }

    return {
        "context": build_response_context(context, "init"),
        "message": {"contract": response_contract},
    }


async def handle_confirm(context: dict, message: dict) -> dict:
    """Handle confirm: BAP confirms. Mark ACTIVE and dispatch to orchestrator."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = await repo.get_contract_by_txn(txn_id)
    if not stored:
        logger.warning(f"confirm: txn unknown to this BPP, rejecting [txn={txn_id[:8]}]")
        return _txn_not_found_response(context, "confirm")

    # Update contract with confirm data (commitments may contain the prompt)
    confirm_commitments = contract.get("commitments", [])
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
        "id": contract.get("id", stored["contract_code"]),
        "commitments": contract.get("commitments", []),
        "participants": contract.get("participants", []),
        "performance": contract.get("performance", _parse_jsonb(stored["performance"])),
        "settlements": contract.get("settlements", []),
    }

    return {
        "context": build_response_context(context, "confirm"),
        "message": {"contract": response_contract},
    }


async def _dispatch_to_orchestrator(txn_id: str, stored: dict) -> None:
    """Fire-and-forget: build a mini-plan and dispatch to orchestrator2."""
    commitments = _parse_jsonb(stored.get("commitments", []))
    if not commitments:
        return

    resources = commitments[0].get("resources", [])
    if not resources:
        return

    agent_beckn_id = resources[0].get("id", "")
    agent_url = "http://agents:3004"
    sla = {}

    agent = await repo.get_agent_by_beckn_id(agent_beckn_id)
    if agent:
        sla = _parse_jsonb(agent.get("sla", {}))
        agent_url = agent.get("access_point_url") or agent_url

    # Extract enriched payload from performanceAttributes (set by BAP pipeline)
    perf_attrs = commitments[0].get("performanceAttributes", {}) or {}

    # Support both enriched format (agent_input + task_description + prompt)
    # and legacy flat format (direct agent payload).
    agent_input = perf_attrs.get("agent_input", perf_attrs)
    task_description = perf_attrs.get("task_description", "")
    prompt = perf_attrs.get("prompt", "")
    input_schema = perf_attrs.get("input_schema")
    output_schema = perf_attrs.get("output_schema")

    # Fallback: extract prompt from resource descriptor (legacy single-agent flow)
    if not agent_input or agent_input is perf_attrs:
        resources_list = commitments[0].get("resources", [])
        if resources_list and not perf_attrs:
            desc = resources_list[0].get("descriptor", {})
            prompt_text = desc.get("longDesc", "") or desc.get("shortDesc", "")
            if prompt_text:
                agent_input = {"prompt": prompt_text}
                prompt = prompt or prompt_text

    # If we still have no schemas, try to get them from the agent DB record
    if agent and (not input_schema or not output_schema):
        ra = _parse_jsonb(agent.get("resource_attributes", {}))
        input_schema = input_schema or ra.get("inputSchema") or ra.get("input_schema")
        output_schema = output_schema or ra.get("outputSchema") or ra.get("output_schema")

    # Only expose to the orchestrator the keys declared in inputSchema.properties.
    # If we mapped all keys from agent_input (which may include format, document,
    # text, etc. injected by the pipeline), the LLM receives irrelevant fields
    # and can build a payload that doesn't match the agent's contract.
    # Fall back to all keys when no schema is available.
    schema_keys = set((input_schema or {}).get("properties", {}).keys())
    if schema_keys and isinstance(agent_input, dict):
        step_input = {k: f"${{input.{k}}}" for k in schema_keys}
    elif isinstance(agent_input, dict):
        step_input = {k: f"${{input.{k}}}" for k in agent_input}
    else:
        step_input = {}

    # Build a single-step plan for orchestrator2
    mini_plan = {
        "goal": task_description or prompt or "Execute agent task",
        "agents": [{
            "agent_name": agent_beckn_id,
            "label": agent_beckn_id,
            "endpoint": f"{agent_url}/task?agent_id={agent_beckn_id}",
            "inputSchema": input_schema or {},
            "outputSchema": output_schema or {},
        }],
        "steps": [{
            "id": "step1",
            "agent": agent_beckn_id,
            "endpoint": f"{agent_url}/task?agent_id={agent_beckn_id}",
            "input": step_input,
        }],
        "executionLayers": [["step1"]],
        "finalOutput": "${step1}",
    }

    try:
        ack = await orchestrator_client.start_execution({
            "plan": mini_plan,
            "prompt": prompt or task_description or "Execute task",
            "data": agent_input if isinstance(agent_input, dict) else {},
        })
        execution_id = ack.get("execution_id")
        await repo.update_contract(txn_id, execution_id=execution_id)
        logger.info("dispatch: txn %s → execution %s (orch2)", txn_id[:8], execution_id)
    except Exception as exc:
        logger.error("dispatch: failed for txn %s: %s", txn_id[:8], exc)


async def handle_status(context: dict, message: dict) -> dict:
    """Handle status: polls orchestrator for execution state."""
    contract = message.get("contract", {})
    txn_id = context["transactionId"]

    stored = await repo.get_contract_by_txn(txn_id)
    if not stored:
        logger.warning(f"status: txn unknown to this BPP, rejecting [txn={txn_id[:8]}]")
        return _txn_not_found_response(context, "status")

    exec_status = "PENDING"
    short_desc = "Execution pending"
    result: dict = {}
    metadata: dict = {}

    execution_id = stored.get("execution_id")
    if execution_id:
        try:
            exec_data = await orchestrator_client.get_execution(execution_id)
            exec_status = exec_data.get("status", "PENDING")
            result = exec_data.get("result") or {}

            # Support both orchestrator v1 (metadata dict) and v2 (execution_summary list)
            metadata = exec_data.get("metadata") or {}
            error = exec_data.get("error")

            # Orchestrator v2: extract error from execution_summary if present
            if not error:
                for step_summary in exec_data.get("execution_summary", []):
                    if step_summary.get("status") == "failed" and step_summary.get("note"):
                        error = step_summary["note"]
                        break

            if exec_status in ("COMPLETED", "PARTIAL"):
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

    stored_commitments = _parse_jsonb(stored["commitments"])
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
                "id": contract.get("id", stored["contract_code"]),
                "commitments": commitments,
                "performance": performance,
            }
        },
    }


async def handle_cancel(context: dict, message: dict) -> dict:
    txn_id = context["transactionId"]
    contract = message.get("contract", {})

    stored = await repo.get_contract_by_txn(txn_id)
    if not stored:
        logger.warning(f"cancel: txn unknown to this BPP, rejecting [txn={txn_id[:8]}]")
        return _txn_not_found_response(context, "cancel")

    await repo.update_contract(txn_id, status="CANCELLED")
    return {
        "context": build_response_context(context, "cancel"),
        "message": {"contract": {**contract, "status": {"code": "CANCELLED"}}},
    }


async def handle_rating(context: dict, message: dict) -> dict:
    # Legacy Beckn v1 echo handler. Real rating ingest lives in
    # ``handle_rate`` below (Beckn v2 verb). Kept for backwards
    # compatibility with any old caller still on v1 wire shape.
    ratings = message.get("ratings", [])
    logger.info(f"rating (v1) received: {ratings}")
    return {
        "context": build_response_context(context, "rating"),
        "message": {"ratings": ratings},
    }


# ── rate (Beckn v2) ──────────────────────────────────────────


# Beckn v2 RateAction range invariants: any rating outside [min, max]
# is malformed and must not enter the ledger.
RATING_MIN_DEFAULT = 1.0
RATING_MAX_DEFAULT = 5.0


def _coerce_rating_input(rinput: dict) -> dict | None:
    """Normalise one ``RatingInput`` block from the BAP into the shape
    we persist. Returns ``None`` when the input is missing required
    fields or the score lies outside its declared range.

    The BAP-side scale (range.min/range.max) is preserved verbatim — a
    partner could submit on a 1..10 scale tomorrow without breaking the
    handler. Our discover aggregator normalises to 0..1 separately.
    """
    target = (rinput or {}).get("target") or {}
    target_id = target.get("id")
    if not target_id:
        return None
    rng = (rinput or {}).get("range") or {}
    if "value" not in rng:
        return None
    score = float(rng.get("value"))
    score_min = float(rng.get("min", RATING_MIN_DEFAULT))
    score_max = float(rng.get("max", RATING_MAX_DEFAULT))
    if score_min >= score_max:
        return None
    if not (score_min <= score <= score_max):
        return None
    feedback = None
    submission = rinput.get("feedbackFormSubmission") or {}
    feedback = (submission.get("data") or {}).get("review")
    # `target.descriptor.code` carries the target type (agent, provider,
    # contract...). Default to "agent" since the marketplace's primary
    # ratable surface is the AI agent.
    target_type = (target.get("descriptor") or {}).get("code") or "agent"
    return {
        "target_id": target_id,
        "target_type": target_type,
        "score": score,
        "score_min": score_min,
        "score_max": score_max,
        "feedback": feedback,
    }


async def _push_rating_to_cds(*, agent_beckn_id: str, score: float,
                              score_min: float, score_max: float) -> None:
    """Best-effort POST to the marketplace CDS ratings ingest.

    Fire-and-forget: a CDS hiccup must NOT roll back the local
    persistence we just committed. The discover quality component
    catches up the next time the BPP rates an agent or the operator
    backfills.
    """
    url = f"{CDS_BASE_URL.rstrip('/')}/cds/ratings/ingest"
    body = {
        "bppSubscriberId": BPP_ID,
        "agentBecknId":    agent_beckn_id,
        "score":           float(score),
        "scoreMin":        float(score_min),
        "scoreMax":        float(score_max),
    }
    try:
        async with httpx.AsyncClient(timeout=CDS_INGEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body)
            logger.info(
                "cds rating ingest %s → HTTP %s", agent_beckn_id, resp.status_code
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cds rating ingest failed for %s: %s", agent_beckn_id, exc)


async def handle_rate(context: dict, message: dict) -> dict:
    """Persist incoming RatingInputs and acknowledge with on_rate.

    Same orphan-txn guard as init/confirm/status: a rate for a
    transaction this BPP has never seen returns a Beckn v2 error
    envelope (code 30002) without inserting anything.

    The on_rate response echoes the accepted RatingInputs back to the
    BAP. A future iteration can attach an aggregate snapshot here
    (the spec allows it); we'll surface ``avg_score`` from the new
    aggregator once the BPP→CDS ingest is wired.
    """
    txn_id = context.get("transactionId", "unknown")
    stored = await repo.get_contract_by_txn(txn_id)
    if not stored:
        logger.warning(f"rate: txn unknown to this BPP, rejecting [txn={txn_id[:8]}]")
        return _txn_not_found_response(context, "rate")

    bap_id = context.get("bapId")
    contract_code = stored.get("contract_code")

    accepted: list[dict] = []
    rejected_count = 0
    for rinput in message.get("ratingInputs") or []:
        coerced = _coerce_rating_input(rinput)
        if coerced is None:
            rejected_count += 1
            continue
        await repo.record_rating_received(
            transaction_id=txn_id,
            contract_code=contract_code,
            target_id=coerced["target_id"],
            target_type=coerced["target_type"],
            score=coerced["score"],
            score_min=coerced["score_min"],
            score_max=coerced["score_max"],
            feedback=coerced["feedback"],
            bap_id=bap_id,
        )
        accepted.append(rinput)
        # Push to CDS aggregator only for agent-targeted ratings — that
        # is what discover scoring reads. Provider/contract ratings are
        # logged locally and not (yet) part of the composite score.
        if coerced["target_type"] == "agent":
            asyncio.create_task(_push_rating_to_cds(
                agent_beckn_id=coerced["target_id"],
                score=coerced["score"],
                score_min=coerced["score_min"],
                score_max=coerced["score_max"],
            ))

    if rejected_count:
        logger.info(
            f"rate: {len(accepted)} accepted, {rejected_count} rejected "
            f"[txn={txn_id[:8]}]"
        )
    else:
        logger.info(f"rate: {len(accepted)} accepted [txn={txn_id[:8]}]")

    return {
        "context": build_response_context(context, "rate"),
        "message": {"ratingInputs": accepted},
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
    # `discover` removed (Pieza 2 of discover v2): the CDS at mock-network
    # owns indexed discovery now. ONIX routes the BAP's discover action
    # straight to the CDS, so the BPP no longer sees it. handle_discover
    # is kept in this file for reference and tests but is unreachable.
    "select": handle_select,
    "init": handle_init,
    "confirm": handle_confirm,
    "status": handle_status,
    "cancel": handle_cancel,
    "rate": handle_rate,
    "rating": handle_rating,
    "support": handle_support,
}
