"""Agent probe orchestration (Epic E).

Two execution modes (the hybrid the team chose):

  ``probe_agent_dryrun``   Cheap, no LLM tokens. Synthesises an input from
                           ``inputSchema`` and checks it validates. Promotes
                           on a declared, satisfiable input contract. Used by
                           the periodic cron over probation agents.

  ``probe_agent_full``     Faithful. Drives the real Beckn flow through the
                           BAP's API (select→init→confirm→status), reads the
                           agent's output, validates it against
                           ``outputSchema`` and checks latency vs SLA. Costs
                           tokens, so it is on-demand only (retry endpoint).

Both converge on ``_evaluate_and_persist``, which records the probe, flips
``agent_versions.probe_status`` (live | failing_probe) and writes an audit row.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from app.probe import repository
from app.probe.synth import synthesize_valid_input, validate_output

logger = logging.getLogger(__name__)

BAP_API_URL = os.getenv("BAP_API_URL", "http://bap-marketplace:3001/api")
# E4: an agent passes the latency check if measured <= 2 * declared SLA.
SLA_TOLERANCE = 2.0
FLOW_CALLBACK_TIMEOUT_S = 30.0


def _facts(agent: dict) -> dict:
    return agent.get("agent_facts") or {}


def _input_schema(agent: dict) -> dict:
    return _facts(agent).get("inputSchema") or {}


def _output_schema(agent: dict) -> dict:
    return _facts(agent).get("outputSchema") or {}


async def _evaluate_and_persist(
    agent: dict,
    *,
    input_payload: Optional[Any],
    input_valid: bool,
    output_payload: Optional[Any] = None,
    output_valid: Optional[bool] = None,
    latency_ms: Optional[int] = None,
    latency_within_sla: Optional[bool] = None,
    failure_reason: Optional[str] = None,
    require_output: bool,
) -> dict:
    """Compute the verdict, record the probe, flip probe_status, audit.

    ``require_output`` distinguishes the two modes: a dry-run passes on
    ``input_valid`` alone; a full run additionally requires
    ``output_valid`` and ``latency_within_sla`` (E5)."""
    if require_output:
        passed = bool(input_valid and output_valid and latency_within_sla)
    else:
        passed = bool(input_valid)

    bpp = agent["bpp_subscriber_id"]
    beckn_id = agent["beckn_id"]
    version = agent.get("version") or "0.0.0"

    await repository.record_probe(
        bpp_subscriber_id=bpp,
        agent_beckn_id=beckn_id,
        agent_version=version,
        input_payload=input_payload if isinstance(input_payload, (dict, list)) else
            ({"value": input_payload} if input_payload is not None else None),
        output_payload=output_payload if isinstance(output_payload, (dict, list)) else
            ({"value": output_payload} if output_payload is not None else None),
        input_valid=input_valid,
        output_valid=output_valid,
        latency_ms=latency_ms,
        latency_within_sla=latency_within_sla,
        passed=passed,
        failure_reason=failure_reason,
    )

    new_status = "live" if passed else "failing_probe"
    await repository.set_probe_status(bpp, beckn_id, probe_status=new_status)

    from app.admission import repository as admission_repository
    await admission_repository.record_audit(
        subscriber_id=bpp,
        action="probe_passed" if passed else "probe_failed",
        actor="system",
        details={
            "agent_beckn_id": beckn_id,
            "input_valid": input_valid,
            "output_valid": output_valid,
            "latency_within_sla": latency_within_sla,
            "failure_reason": failure_reason,
        },
    )

    logger.info(
        "probe: %s/%s -> %s (input_valid=%s output_valid=%s sla_ok=%s)",
        bpp, beckn_id, new_status, input_valid, output_valid, latency_within_sla,
    )
    return {
        "bpp_subscriber_id": bpp,
        "agent_beckn_id": beckn_id,
        "probe_status": new_status,
        "passed": passed,
        "input_valid": input_valid,
        "output_valid": output_valid,
        "latency_ms": latency_ms,
        "latency_within_sla": latency_within_sla,
        "failure_reason": failure_reason,
    }


# ─── Dry-run mode (cron) ────────────────────────────────────────────


async def probe_agent_dryrun(agent: dict) -> dict:
    """Synthesise + validate input only. No execution, no tokens."""
    input_schema = _input_schema(agent)
    if not input_schema:
        return await _evaluate_and_persist(
            agent, input_payload=None, input_valid=False,
            failure_reason="agent declares no inputSchema", require_output=False,
        )
    payload, errors = synthesize_valid_input(input_schema)
    return await _evaluate_and_persist(
        agent,
        input_payload=payload,
        input_valid=not errors,
        failure_reason=("; ".join(errors)[:500] if errors else None),
        require_output=False,
    )


async def probe_all_probation(limit: int = 50) -> list[dict]:
    """Cron entry point: dry-run every probation agent of an active BPP."""
    agents = await repository.list_probation_agents(limit=limit)
    results = []
    for agent in agents:
        try:
            results.append(await probe_agent_dryrun(agent))
        except Exception as exc:  # noqa: BLE001 — one bad agent must not stop the sweep
            logger.warning("probe: dry-run crashed for %s/%s: %s",
                           agent.get("bpp_subscriber_id"), agent.get("beckn_id"), exc)
    if results:
        logger.info("probe: dry-run sweep promoted %d/%d agents",
                    sum(1 for r in results if r["passed"]), len(results))
    return results


# ─── Full Beckn-flow mode (on-demand retry) ─────────────────────────


async def probe_agent_full(agent: dict) -> dict:
    """Drive the real Beckn flow through the BAP API and validate output.

    Best-effort: if the BAP/BPP flow cannot complete (unreachable, no
    callback, unparseable output) the probe fails with a recorded reason
    rather than raising — the agent simply does not get promoted."""
    input_schema = _input_schema(agent)
    output_schema = _output_schema(agent)
    payload, in_errors = synthesize_valid_input(input_schema) if input_schema else (None, ["no inputSchema"])
    input_valid = not in_errors and input_schema != {}

    if not input_valid:
        return await _evaluate_and_persist(
            agent, input_payload=payload, input_valid=False,
            output_valid=False, latency_within_sla=False,
            failure_reason=("input synthesis failed: " + "; ".join(in_errors))[:500],
            require_output=True,
        )

    # Resolve routing for the select.
    bpp_id = agent["bpp_subscriber_id"]
    beckn_id = agent["beckn_id"]
    from app.registry import repository as registry_repository
    subscriber = await registry_repository.get_subscriber(bpp_id)
    bpp_uri = (subscriber or {}).get("endpoint_url")
    offer_id = _facts(agent).get("offerId") or f"offer-{beckn_id}"

    started = time.perf_counter()
    output, reason = await _run_beckn_flow(
        agent_id=beckn_id, offer_id=offer_id, bpp_id=bpp_id,
        bpp_uri=bpp_uri, agent_input=payload,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    if output is None:
        return await _evaluate_and_persist(
            agent, input_payload=payload, input_valid=True,
            output_payload=None, output_valid=False,
            latency_ms=latency_ms, latency_within_sla=False,
            failure_reason=reason, require_output=True,
        )

    out_errors = validate_output(output, output_schema) if output_schema else \
        ["agent declares no outputSchema"]
    output_valid = not out_errors

    sla = agent.get("sla_max_latency_ms")
    latency_within_sla = True if not sla else latency_ms <= SLA_TOLERANCE * sla

    fail_reason = None
    if not output_valid:
        fail_reason = ("output failed schema: " + "; ".join(out_errors))[:500]
    elif not latency_within_sla:
        fail_reason = f"latency {latency_ms}ms exceeds {SLA_TOLERANCE}x SLA ({sla}ms)"

    return await _evaluate_and_persist(
        agent, input_payload=payload, input_valid=True,
        output_payload=output, output_valid=output_valid,
        latency_ms=latency_ms, latency_within_sla=latency_within_sla,
        failure_reason=fail_reason, require_output=True,
    )


async def _run_beckn_flow(
    *, agent_id: str, offer_id: str, bpp_id: str,
    bpp_uri: Optional[str], agent_input: dict,
) -> tuple[Optional[Any], Optional[str]]:
    """Drive select→init→confirm→status against the BAP API as an external
    client. Returns (agent_output, failure_reason). On any gap, output is
    None and the reason explains why."""
    select_body: dict = {"agent_id": agent_id, "offer_id": offer_id}
    if bpp_id:
        select_body["bpp_id"] = bpp_id
    if bpp_uri:
        select_body["bpp_uri"] = bpp_uri

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            async def _count() -> int:
                r = await client.get(f"{BAP_API_URL}/callbacks/count")
                return r.json().get("callbacks_recibidos", 0)

            base = await _count()
            sel = await client.post(f"{BAP_API_URL}/contracts/select", json=select_body)
            txn_id = sel.json().get("transactionId")
            if not txn_id:
                return None, "select did not return a transactionId"
            if not await _wait_callbacks(client, base + 1):
                return None, "on_select callback not received"

            await client.post(f"{BAP_API_URL}/contracts/init",
                              json={"transaction_id": txn_id, "agent_input": agent_input})
            await _wait_callbacks(client, base + 2)

            await client.post(f"{BAP_API_URL}/contracts/confirm",
                              json={"transaction_id": txn_id, "agent_input": agent_input})
            await _wait_callbacks(client, base + 3)

            await client.post(f"{BAP_API_URL}/contracts/status",
                              json={"transaction_id": txn_id})
            await _wait_callbacks(client, base + 4)

            txn = await client.get(f"{BAP_API_URL}/transactions/{txn_id}")
            return _extract_output(txn.json()), None
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        return None, f"BAP flow unreachable: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"BAP flow error: {type(exc).__name__}: {exc}"


async def _wait_callbacks(client: httpx.AsyncClient, target: int,
                          timeout: float = FLOW_CALLBACK_TIMEOUT_S) -> bool:
    import asyncio
    waited = 0.0
    while waited < timeout:
        r = await client.get(f"{BAP_API_URL}/callbacks/count")
        if r.json().get("callbacks_recibidos", 0) >= target:
            return True
        await asyncio.sleep(1.0)
        waited += 1.0
    return False


def _extract_output(transaction: dict) -> Optional[Any]:
    """Pull the agent's structured result out of the stored transaction.

    The on_status callback carries the agent output; its exact location
    has drifted across iterations, so we probe a few known shapes and
    return the first structured object we find."""
    if not isinstance(transaction, dict):
        return None
    # Common locations, most-specific first.
    candidates = [
        transaction.get("agent_output"),
        transaction.get("result"),
        (transaction.get("on_status") or {}).get("result")
            if isinstance(transaction.get("on_status"), dict) else None,
    ]
    for c in candidates:
        if isinstance(c, (dict, list)) and c:
            return c
    # Fall back to digging for a performanceAttributes.result anywhere shallow.
    contract = transaction.get("contract") or transaction.get("message", {}).get("contract")
    if isinstance(contract, dict):
        commitments = contract.get("commitments") or []
        for c in commitments:
            perf = (c or {}).get("performance") or {}
            res = perf.get("result") or perf.get("output")
            if isinstance(res, (dict, list)) and res:
                return res
    return None
