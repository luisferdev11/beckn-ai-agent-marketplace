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
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.catalog_data import get_agent_by_id, get_offer_by_id, PROVIDER
from app.config import AGENT_URL_MAP, BPP_ID, BPP_URI, CDS_BASE_URL
from app.handlers import orchestrator_client

CDS_INGEST_TIMEOUT_SECONDS = 3.0

logger = logging.getLogger(__name__)

# In-memory contract store (Iter 0 — will migrate to SQLite/Postgres)
_contracts: dict[str, dict] = {}

# In-memory ratings store. Same iteration debt as `_contracts`: Serg's
# postgres migration is tracked as separate follow-up. Keyed by
# (transaction_id, target_id, target_type) to enforce upsert semantics
# without a unique index.
_ratings_received: list[dict] = []

# Beckn v2 RatingInput range invariants — see services/bpp/app/handlers
# for the canonical implementation.
RATING_MIN_DEFAULT = 1.0
RATING_MAX_DEFAULT = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def build_response_context(incoming_context: dict, action: str) -> dict:
    """
    Build the on_* callback context from the incoming context.

    Self-identify: even when the discover arrives with the BAP's default
    bppId (because the DS fan-out is symmetric), this BPP must replace it
    with its own identity so that ONIX-BPP-Serg can sign with its own
    keypair and the BAP can attribute the catalog to the right provider.
    """
    ctx = {**incoming_context}
    ctx["action"] = f"on_{action}"
    ctx["timestamp"] = _now_iso()
    ctx["bppId"] = BPP_ID
    ctx["bppUri"] = BPP_URI
    return ctx


async def handle_discover(context: dict, message: dict) -> dict:
    """
    Handle discover: BAP is looking for available AI agents.
    Returns on_discover with the full catalog (provider + resources + offers).

    Beckn v2 expects `message.catalogs` (array). We return one catalog —
    the BAP merges catalogs from every BPP that responds.
    """
    from app.catalog_data import get_catalog_for_publish
    catalog = get_catalog_for_publish()
    logger.info("discover: returning catalog with %d agents", len(catalog.get("resources", [])))
    return {
        "context": build_response_context(context, "discover"),
        "message": {"catalogs": [catalog]},
    }


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

    # Build consideration (pricing) based on the requested resources.
    # Currency follows the agent's catalog pricing — MXN for Serg agents.
    considerations = []
    for commitment in commitments:
        resources = commitment.get("resources", [])
        offer_ref = commitment.get("offer", {})
        offer = get_offer_by_id(offer_ref.get("id", ""))

        total_price = 0.0
        currency = "MXN"
        breakup = []
        for res in resources:
            agent = get_agent_by_id(res.get("id", ""))
            qty = res.get("quantity", {}).get("unitQuantity", 1)
            if agent:
                attrs = agent.get("resourceAttributes", {})
                pricing = attrs.get("pricing", {})
                unit_price = pricing.get("unitPrice", 0)
                currency = pricing.get("currency", currency)
                line_total = unit_price * qty
                total_price += line_total
                breakup.append({
                    "title": f"{agent['descriptor']['name']} x{qty}",
                    "price": {"currency": currency, "value": f"{line_total:.2f}"},
                })

        # Add taxes (18%) — labeled VAT for MXN, GST for INR
        tax_label = "VAT (18%)" if currency == "MXN" else "GST (18%)"
        tax = total_price * 0.18
        breakup.append({"title": tax_label, "price": {"currency": currency, "value": f"{tax:.2f}"}})

        considerations.append({
            "id": f"consideration-{commitment.get('id', '001')}",
            "price": {"currency": currency, "value": f"{total_price + tax:.2f}"},
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
        # The confirm message carries the latest commitments — including any
        # performanceAttributes the BAP wants the agent to receive as input.
        # Persist them so dispatch picks up the right payload.
        incoming_commitments = contract.get("commitments") or []
        if incoming_commitments:
            stored["commitments"] = incoming_commitments
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
    """Fire-and-forget: build a mini-plan and dispatch to orchestrator2."""
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

    # Extract enriched payload from performanceAttributes (set by BAP pipeline).
    # Support both enriched format (agent_input + task_description + prompt)
    # and legacy flat format (direct agent payload).
    perf_attrs = commitments[0].get("performanceAttributes", {}) or {}
    agent_input = perf_attrs.get("agent_input", perf_attrs)
    task_description = perf_attrs.get("task_description", "")
    prompt = perf_attrs.get("prompt", "")
    input_schema = perf_attrs.get("input_schema")
    output_schema = perf_attrs.get("output_schema")

    # Fallback: extract prompt from resource descriptor (legacy single-agent flow)
    if not agent_input or agent_input is perf_attrs:
        desc = resources[0].get("descriptor", {})
        prompt_text = desc.get("longDesc", "") or desc.get("shortDesc", "")
        if prompt_text:
            agent_input = {"text": prompt_text}
            prompt = prompt or prompt_text

    # Get schemas from in-memory catalog if not provided by BAP
    if not input_schema or not output_schema:
        agent_catalog = get_agent_by_id(agent_id)
        if agent_catalog:
            ra = agent_catalog.get("resourceAttributes", {})
            input_schema = input_schema or ra.get("inputSchema")
            output_schema = output_schema or ra.get("outputSchema")

    # Only expose to the orchestrator the keys declared in inputSchema.properties.
    # Fall back to all keys when no schema is available.
    schema_keys = set((input_schema or {}).get("properties", {}).keys())
    if schema_keys and isinstance(agent_input, dict):
        step_input = {k: f"${{input.{k}}}" for k in schema_keys}
    elif isinstance(agent_input, dict):
        step_input = {k: f"${{input.{k}}}" for k in agent_input}
    else:
        step_input = {}

    # Build a single-step plan compatible with orchestrator2
    mini_plan = {
        "goal": task_description or prompt or "Execute agent task",
        "agents": [{
            "agent_name": agent_id,
            "label": agent_id,
            "endpoint": f"{agent_url}/task?agent_id={agent_id}",
            "inputSchema": input_schema or {},
            "outputSchema": output_schema or {},
        }],
        "steps": [{
            "id": "step1",
            "agent": agent_id,
            "endpoint": f"{agent_url}/task?agent_id={agent_id}",
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
        stored["execution_id"] = ack.get("execution_id")
        logger.info("dispatch: contract %s → execution %s (orch2)", contract_id, stored["execution_id"])
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
    result: dict = {}
    metadata: dict = {}

    execution_id = stored.get("execution_id") if stored else None
    if execution_id:
        try:
            exec_data = await orchestrator_client.get_execution(execution_id)
            exec_status = exec_data.get("status", "PENDING")
            result = exec_data.get("result")
            # orchestrator2 has no metadata dict; keep for any future v1 fallback
            metadata = exec_data.get("metadata") or {}
            error = exec_data.get("error")

            # orchestrator2: extract error from execution_summary if present
            if not error:
                for step_summary in exec_data.get("execution_summary", []):
                    if step_summary.get("status") == "failed" and step_summary.get("note"):
                        error = step_summary["note"]
                        break

            if exec_status in ("COMPLETED", "PARTIAL"):
                # Serg agents return plain strings; Tecla agents return dicts.
                # orchestrator2 wraps raw result + human-readable response.
                if isinstance(result, dict):
                    short_desc = (
                        result.get("response")
                        or result.get("review")
                        or result.get("summary")
                        or result.get("output")
                        or str(result)
                    )
                elif isinstance(result, str):
                    short_desc = result
                else:
                    short_desc = str(result) if result is not None else "Execution completed"
            elif exec_status == "FAILED":
                short_desc = error or "Agent execution failed"
            else:
                short_desc = f"Execution {exec_status.lower()}"
        except Exception as exc:
            logger.error("status: failed to poll orchestrator for execution %s: %s", execution_id, exc)
            short_desc = "Could not retrieve execution status"

    # Extended schema validation is disabled in ONIX (extendedSchema_enabled: false) —
    # ONIX only checks @context and @type are present (base validation).
    schema_url = "https://raw.githubusercontent.com/luisferdev11/beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json"
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
            "startedAt": metadata.get("started_at") or (stored.get("confirmed_at") if stored else _now_iso()),
            "completedAt": metadata.get("completed_at") or _now_iso(),
            "latencyMs": metadata.get("latency_ms") or 0,
            "tokensUsed": metadata.get("tokens_used") or {"input": 0, "output": 0, "total": 0},
            "model": metadata.get("model") or "unknown",
            "result": result,
            "status": exec_status,
        },
    }]

    commitments = stored.get("commitments", []) if stored else contract.get("commitments", [])
    if not commitments:
        commitments = [{"id": "commitment-001", "status": {"code": "ACTIVE"},
                        "resources": [{"id": "summarizer-v1",
                                       "descriptor": {"name": "AI Agent", "code": "AAS-001"},
                                       "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
                        "offer": {"id": "offer-summarizer-v1", "resourceIds": ["summarizer-v1"]}}]

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
    """Legacy v1 rating echo handler. Real ingestion lives in handle_rate."""
    ratings = message.get("ratings", [])
    logger.info(f"rating (v1) received: {ratings}")
    return {
        "context": build_response_context(context, "rating"),
        "message": {"ratings": ratings},
    }


def _coerce_rating_input(rinput: dict) -> dict | None:
    """Same shape as services/bpp/app/handlers/beckn_actions.py — kept
    duplicated by design (Serg is an independent deployable that may
    evolve its rating rules separately)."""
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
    target_type = (target.get("descriptor") or {}).get("code") or "agent"
    return {
        "target_id": target_id,
        "target_type": target_type,
        "score": score,
        "score_min": score_min,
        "score_max": score_max,
        "feedback": feedback,
    }


def _upsert_rating(*, transaction_id, contract_id, bap_id, coerced):
    for row in _ratings_received:
        if (row["transaction_id"] == transaction_id
                and row["target_id"] == coerced["target_id"]
                and row["target_type"] == coerced["target_type"]):
            row.update({
                "score": coerced["score"],
                "score_min": coerced["score_min"],
                "score_max": coerced["score_max"],
                "feedback": coerced["feedback"],
                "bap_id": bap_id,
            })
            return row
    new_row = {
        "transaction_id": transaction_id,
        "contract_code": contract_id,
        "target_id": coerced["target_id"],
        "target_type": coerced["target_type"],
        "score": coerced["score"],
        "score_min": coerced["score_min"],
        "score_max": coerced["score_max"],
        "feedback": coerced["feedback"],
        "bap_id": bap_id,
        "received_at": _now_iso(),
    }
    _ratings_received.append(new_row)
    return new_row


async def _push_rating_to_cds(*, agent_beckn_id, score, score_min, score_max):
    """Best-effort POST to the marketplace CDS ratings ingest. Errors
    are logged and swallowed — the local rating is already persisted."""
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
    """Persist incoming RatingInputs (in-memory) and ack with on_rate.

    Orphan-txn rejection mirrors Tecla — Serg's contract store is the
    in-memory ``_contracts`` map; a rate without a prior select on this
    BPP gets silently dropped (no row written).
    """
    txn_id = context.get("transactionId", "unknown")
    stored = None
    for c in _contracts.values():
        if c.get("transaction_id") == txn_id:
            stored = c
            break
    if stored is None:
        logger.warning(f"rate: txn unknown to Serg, rejecting [txn={txn_id[:8]}]")
        return {
            "context": build_response_context(context, "rate"),
            "message": {"ratingInputs": []},
        }

    bap_id = context.get("bapId")
    contract_id = stored.get("id")

    accepted: list[dict] = []
    for rinput in message.get("ratingInputs") or []:
        coerced = _coerce_rating_input(rinput)
        if coerced is None:
            continue
        _upsert_rating(
            transaction_id=txn_id,
            contract_id=contract_id,
            bap_id=bap_id,
            coerced=coerced,
        )
        accepted.append(rinput)
        if coerced["target_type"] == "agent":
            asyncio.create_task(_push_rating_to_cds(
                agent_beckn_id=coerced["target_id"],
                score=coerced["score"],
                score_min=coerced["score_min"],
                score_max=coerced["score_max"],
            ))

    logger.info(f"rate: {len(accepted)} accepted [txn={txn_id[:8]}]")
    return {
        "context": build_response_context(context, "rate"),
        "message": {"ratingInputs": accepted},
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
    # `discover` removed (Pieza 2 of discover v2): the CDS at mock-network
    # owns indexed discovery now. handle_discover stays in this file as
    # reference but is unreachable from the dispatcher.
    "select": handle_select,
    "init": handle_init,
    "confirm": handle_confirm,
    "status": handle_status,
    "cancel": handle_cancel,
    "rate": handle_rate,
    "rating": handle_rating,
    "support": handle_support,
}
