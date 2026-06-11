"""run_plan() — state machine that orchestrates a multi-agent execution plan.

States: UNDERSTAND_TASK → (per step: DEFINE_PROMPT → EXECUTE_AGENT → VALIDATE_RESPONSE) → DELIVER_RESULT
Steps in the same executionLayer run with asyncio.gather().
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.config import (
    AGENT_BACKOFF_SECONDS,
    AGENT_MAX_RETRIES,
    VALIDATION_MAX_RETRIES,
)
from app.executor.interpolator import interpolate
from app.executor.models import (
    CompletedStep,
    ConversationEntry,
    ErrorEntry,
    ExecutionStatus,
    OrchestrationRecord,
    StepStatus,
)
from app.executor.state_machine import OrchestratorState
from app.executor.store import store_update
from app.llm_client import GroqClient

logger = logging.getLogger(__name__)

llm = GroqClient()
_http_client = httpx.AsyncClient(timeout=30.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_transition(record: OrchestrationRecord, new_state: OrchestratorState, step_id: str | None = None) -> None:
    old = record.current_state.value
    record.current_state = new_state
    label = f"[{record.execution_id}]"
    if step_id:
        label += f"[{step_id}]"
    logger.info("%s %s → %s", label, old, new_state.value)


def _log_conversation(record: OrchestrationRecord, action: str, step_id: str | None, detail: Any) -> None:
    record.conversation_log.append(ConversationEntry(
        action=action, step_id=step_id, timestamp=time.time(), detail=detail,
    ))


def _build_agents_index(plan: dict) -> dict[str, dict]:
    """Map agent_name → agent definition from the plan."""
    return {a["agent_name"]: a for a in plan.get("agents", [])}


def _find_dependents(step_id: str, steps: list[dict]) -> set[str]:
    """Find all step ids that transitively depend on step_id."""
    direct = {s["id"] for s in steps if step_id in s.get("dependsOn", [])}
    transitive: set[str] = set()
    queue = list(direct)
    while queue:
        sid = queue.pop()
        if sid not in transitive:
            transitive.add(sid)
            queue.extend(s["id"] for s in steps if sid in s.get("dependsOn", []))
    return transitive


# ── Agent HTTP call with retry ────────────────────────────────────────────────

async def _call_agent(endpoint: str, payload: dict, timeout_ms: int = 30000) -> dict:
    """POST to AGENT endpoint with exponential backoff retry.

    Returns the parsed JSON response dict.
    Raises RuntimeError if all retries fail.
    """
    timeout_s = max(timeout_ms / 1000, 1.0)
    last_error: Exception | None = None

    for attempt in range(1 + AGENT_MAX_RETRIES):
        try:
            resp = await _http_client.post(endpoint, json=payload, timeout=timeout_s)
            if 200 <= resp.status_code < 300:
                if not resp.content:
                    return {"status": "success", "result": {"success": True}, "error": None, "usage": {}}
                body = resp.json()
                return _normalize_agent_response(body)
            # 4xx = payload/client error — retrying won't help
            if 400 <= resp.status_code < 500:
                raise RuntimeError(f"AGENT HTTP {resp.status_code}: {resp.text[:200]}")
            last_error = RuntimeError(f"AGENT HTTP {resp.status_code}: {resp.text[:200]}")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc

        if attempt < AGENT_MAX_RETRIES:
            wait = AGENT_BACKOFF_SECONDS[min(attempt, len(AGENT_BACKOFF_SECONDS) - 1)]
            logger.warning("AGENT call failed (attempt %d/%d), retrying in %ds: %s",
                           attempt + 1, 1 + AGENT_MAX_RETRIES, wait, last_error)
            await asyncio.sleep(wait)

    raise RuntimeError(f"AGENT unreachable after {1 + AGENT_MAX_RETRIES} attempts: {last_error}")


def _normalize_agent_response(body: dict) -> dict:
    """Normalize different agent response formats into a canonical envelope.

    Canonical: {"status": "success"|"error", "result": {...}, "error": ..., "usage": {...}}

    Real agents return: {"agent": "name", "output": {...}}
    Orchestrator v1 agents return: {"status": "success", "result": {...}, "usage": {...}}
    """
    if "result" in body and "status" in body:
        return body

    if "output" in body:
        return {
            "status": "success",
            "result": body["output"],
            "error": None,
            "usage": body.get("usage", {}),
        }

    if "error" in body and "output" not in body and "result" not in body:
        return {
            "status": "error",
            "result": None,
            "error": body["error"],
            "usage": body.get("usage", {}),
        }

    return {"status": "success", "result": body, "error": None, "usage": {}}


# ── Single step execution ─────────────────────────────────────────────────────

async def _execute_step(
    record: OrchestrationRecord,
    step: dict,
    agents_index: dict[str, dict],
) -> None:
    """Execute one step through the DEFINE_PROMPT → EXECUTE_AGENT → VALIDATE_RESPONSE cycle."""
    step_id = step["id"]
    agent_name = step["agent"]
    endpoint = step["endpoint"]
    agent_def = agents_index.get(agent_name, {})
    input_schema = agent_def.get("inputSchema", {})
    output_schema = agent_def.get("outputSchema", {})

    step_note = ""
    if record.execution_brief and "step_notes" in record.execution_brief:
        step_note = record.execution_brief["step_notes"].get(step_id, "")

    record.step_statuses[step_id] = StepStatus.RUNNING
    attempts = 0
    fix_instructions = ""
    agent_result = None  # ensure defined even if all rounds exit via agent-error continue

    for validation_round in range(1 + VALIDATION_MAX_RETRIES):
        # ── DEFINE_PROMPT ─────────────────────────────────────────────
        _log_transition(record, OrchestratorState.DEFINE_PROMPT, step_id)

        interpolated_data = interpolate(step.get("input", {}), record.completed_steps, record.data)
        logger.info("[%s][%s] Interpolated data: %s", record.execution_id, step_id,
                     json.dumps(interpolated_data, ensure_ascii=False)[:500])

        payload = await llm.build_payload(
            input_schema=input_schema,
            step_note=step_note,
            interpolated_data=interpolated_data,
            completed_steps=record.completed_steps,
            fix_instructions=fix_instructions,
        )
        logger.info("[%s][%s] ORCHESTRATOR-LLM built payload: %s", record.execution_id, step_id,
                     json.dumps(payload, ensure_ascii=False)[:500])
        _log_conversation(record, "DEFINE_PROMPT", step_id, {"payload": payload, "fix_instructions": fix_instructions})

        # ── EXECUTE_AGENT ─────────────────────────────────────────────
        _log_transition(record, OrchestratorState.EXECUTE_AGENT, step_id)
        attempts += 1
        logger.info("[%s][%s] Calling AGENT %s at %s with payload: %s",
                     record.execution_id, step_id, agent_name, endpoint,
                     json.dumps(payload, ensure_ascii=False)[:500])

        try:
            agent_response = await _call_agent(endpoint, payload)
        except RuntimeError as exc:
            record.error_log.append(ErrorEntry(
                step_id=step_id, attempt=attempts, error=str(exc), timestamp=time.time(),
            ))
            _log_conversation(record, "EXECUTE_AGENT_FAILED", step_id, {"error": str(exc)})
            # If retries remain, let the LLM rebuild the payload
            if validation_round < VALIDATION_MAX_RETRIES:
                fix_instructions = f"Agent call failed: {exc}. Rebuild the payload to fix this."
                logger.warning("[%s][%s] Agent call failed (round %d/%d) — will retry with corrected payload",
                               record.execution_id, step_id, validation_round + 1, 1 + VALIDATION_MAX_RETRIES)
                continue
            record.step_statuses[step_id] = StepStatus.FAILED
            return

        logger.info("[%s][%s] AGENT response: %s", record.execution_id, step_id,
                     json.dumps(agent_response, ensure_ascii=False)[:500])
        _log_conversation(record, "EXECUTE_AGENT", step_id, {"response_status": agent_response.get("status")})

        # Handle agent-level error in the response envelope
        if agent_response.get("status") == "error":
            error_msg = agent_response.get("error", "Unknown agent error")
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_msg))
            record.error_log.append(ErrorEntry(
                step_id=step_id, attempt=attempts, error=str(error_msg), timestamp=time.time(),
            ))
            _log_conversation(record, "AGENT_ERROR", step_id, {"error": error_msg})
            # Let the LLM rebuild the payload with the error as fix_instructions
            fix_instructions = f"Agent rejected the payload with error: {error_msg}. Rebuild the payload to fix this."
            logger.warning("[%s][%s] Agent error (round %d/%d): %s — will retry with corrected payload",
                           record.execution_id, step_id, validation_round + 1, 1 + VALIDATION_MAX_RETRIES, error_msg)
            continue

        agent_result = agent_response.get("result")

        # ── VALIDATE_RESPONSE ─────────────────────────────────────────
        _log_transition(record, OrchestratorState.VALIDATE_RESPONSE, step_id)

        verdict = await llm.validate(
            output_schema=output_schema,
            agent_payload=payload,
            agent_response=agent_result,
            step_note=step_note,
            completed_steps=record.completed_steps,
        )
        _log_conversation(record, "VALIDATE_RESPONSE", step_id, verdict)

        if verdict.get("valid", True):
            # Success — store result
            record.completed_steps[step_id] = CompletedStep(
                output=agent_result,
                step_note=step_note,
                attempts=attempts,
                timestamp=time.time(),
            )
            record.step_statuses[step_id] = StepStatus.SUCCESS
            logger.info("[%s][%s] Step completed successfully (attempts: %d)", record.execution_id, step_id, attempts)
            return

        # Invalid — prepare retry with fix_instructions
        fix_instructions = verdict.get("fix_instructions", "")
        logger.warning(
            "[%s][%s] Validation failed (round %d/%d): %s",
            record.execution_id, step_id, validation_round + 1, 1 + VALIDATION_MAX_RETRIES,
            verdict.get("reason", ""),
        )

    # All validation retries exhausted — attempt to reshape the last response
    # via the LLM rather than failing outright. The agent's code is fixed so
    # retrying the same call won't change its output format.
    if agent_result is not None and output_schema:
        logger.info("[%s][%s] Attempting LLM reshape of agent output to match outputSchema",
                     record.execution_id, step_id)
        _log_conversation(record, "RESHAPE_ATTEMPT", step_id,
                          {"agent_result": agent_result, "output_schema": output_schema})
        try:
            reshaped = await llm.reshape_output(
                output_schema=output_schema,
                agent_response=agent_result,
                step_note=step_note,
            )
            if reshaped:
                record.completed_steps[step_id] = CompletedStep(
                    output=reshaped,
                    step_note=step_note,
                    attempts=attempts,
                    timestamp=time.time(),
                )
                record.step_statuses[step_id] = StepStatus.SUCCESS
                logger.info("[%s][%s] Reshape succeeded — step marked SUCCESS", record.execution_id, step_id)
                _log_conversation(record, "RESHAPE_SUCCESS", step_id, {"reshaped": reshaped})
                return
        except Exception as exc:
            logger.warning("[%s][%s] Reshape failed: %s", record.execution_id, step_id, exc)
            _log_conversation(record, "RESHAPE_FAILED", step_id, {"error": str(exc)})

    record.error_log.append(ErrorEntry(
        step_id=step_id, attempt=attempts,
        error=f"Validation failed after {1 + VALIDATION_MAX_RETRIES} rounds",
        timestamp=time.time(),
    ))
    record.step_statuses[step_id] = StepStatus.FAILED


# ── Main orchestration loop ───────────────────────────────────────────────────

async def run_plan(record: OrchestrationRecord) -> None:
    """Main entry point. Runs the full orchestration state machine.

    Never raises — all failures are captured in the record.
    """
    execution_id = record.execution_id
    plan = record.plan

    try:
        await store_update(execution_id, status=ExecutionStatus.RUNNING)

        goal = plan.get("goal", "")
        record.goal = goal
        steps = plan.get("steps", [])
        layers = plan.get("executionLayers", [])
        agents_index = _build_agents_index(plan)

        # Initialize step statuses
        for s in steps:
            record.step_statuses[s["id"]] = StepStatus.PENDING
        record.pending_steps = [s["id"] for s in steps]

        steps_by_id = {s["id"]: s for s in steps}

        # ── UNDERSTAND_TASK ───────────────────────────────────────────
        _log_transition(record, OrchestratorState.UNDERSTAND_TASK)
        _log_conversation(record, "UNDERSTAND_TASK_START", None, {"goal": goal, "prompt": record.prompt})

        execution_brief = await llm.understand(
            goal=goal, prompt=record.prompt, data=record.data, steps=steps,
        )
        record.execution_brief = execution_brief
        _log_conversation(record, "UNDERSTAND_TASK_DONE", None, execution_brief)
        logger.info("[%s] Execution brief ready: %s", execution_id, execution_brief.get("interpreted_goal", ""))

        # ── Execute layers ────────────────────────────────────────────
        for layer_idx, layer_step_ids in enumerate(layers):
            record.current_layer = layer_idx
            logger.info("[%s] Starting layer %d: %s", execution_id, layer_idx, layer_step_ids)

            # Filter out steps that should be skipped
            runnable: list[dict] = []
            for sid in layer_step_ids:
                step = steps_by_id.get(sid)
                if step is None:
                    continue
                # Skip if any dependency failed
                deps = step.get("dependsOn", [])
                failed_deps = [d for d in deps if record.step_statuses.get(d) in (StepStatus.FAILED, StepStatus.SKIPPED)]
                if failed_deps:
                    record.step_statuses[sid] = StepStatus.SKIPPED
                    dependents = _find_dependents(sid, steps)
                    for dep_id in dependents:
                        record.step_statuses[dep_id] = StepStatus.SKIPPED
                    logger.warning("[%s][%s] Skipped — depends on failed: %s", execution_id, sid, failed_deps)
                    _log_conversation(record, "STEP_SKIPPED", sid, {"failed_deps": failed_deps})
                    continue
                runnable.append(step)

            if runnable:
                await asyncio.gather(*[
                    _execute_step(record, step, agents_index) for step in runnable
                ])

            # Remove completed/failed/skipped from pending
            for sid in layer_step_ids:
                if sid in record.pending_steps:
                    record.pending_steps.remove(sid)

        # ── DELIVER_RESULT ────────────────────────────────────────────
        _log_transition(record, OrchestratorState.DELIVER_RESULT)

        final_output_template = plan.get("finalOutput", {})
        result = interpolate(final_output_template, record.completed_steps, record.data)

        execution_summary = []
        for s in steps:
            sid = s["id"]
            step_status = record.step_statuses.get(sid, StepStatus.PENDING)
            cs = record.completed_steps.get(sid)
            note = None
            if step_status == StepStatus.FAILED:
                # Surface the actual error from error_log
                step_errors = [e.error for e in record.error_log if e.step_id == sid]
                note = step_errors[-1] if step_errors else "unknown failure"
            elif step_status == StepStatus.SKIPPED:
                failed_deps = [d for d in s.get("dependsOn", [])
                               if record.step_statuses.get(d) in (StepStatus.FAILED, StepStatus.SKIPPED)]
                note = f"Dependency failed: {failed_deps}" if failed_deps else "skipped — dependency failed"
            elif cs and cs.output == {"success": True}:
                note = "side-effect only, no output"

            execution_summary.append({
                "step_id": sid,
                "agent": s["agent"],
                "status": step_status.value,
                "attempts": cs.attempts if cs else 0,
                "note": note,
            })

        record.execution_summary = execution_summary

        # ── SYNTHESIZE — convert raw JSON result to human-readable text ──
        if result and any(s == StepStatus.SUCCESS for s in record.step_statuses.values()):
            try:
                synthesized = await llm.synthesize(
                    goal=goal,
                    prompt=record.prompt,
                    raw_result=result,
                )
                if synthesized:
                    result = {"raw": result, **synthesized}
                    _log_conversation(record, "SYNTHESIZE", None, {"synthesized_keys": list(synthesized.keys()) if isinstance(synthesized, dict) else "text"})
            except Exception as exc:
                logger.warning("[%s] Synthesize failed, returning raw result: %s", execution_id, exc)

        record.result = result

        # Determine final status
        statuses = set(record.step_statuses.values())
        if statuses <= {StepStatus.SUCCESS}:
            final_status = ExecutionStatus.COMPLETED
        elif StepStatus.SUCCESS in statuses and (StepStatus.FAILED in statuses or StepStatus.SKIPPED in statuses):
            final_status = ExecutionStatus.PARTIAL
        else:
            final_status = ExecutionStatus.FAILED

        await store_update(execution_id, status=final_status, result=result, execution_summary=execution_summary)
        _log_conversation(record, "DELIVER_RESULT", None, {"status": final_status.value})
        logger.info("[%s] Orchestration finished: %s", execution_id, final_status.value)

    except Exception as exc:
        logger.exception("[%s] Orchestration failed with unhandled error", execution_id)
        record.error_log.append(ErrorEntry(
            step_id="__orchestrator__", attempt=0, error=str(exc), timestamp=time.time(),
        ))
        await store_update(execution_id, status=ExecutionStatus.FAILED)
