from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any, Optional

import httpx

from app.models import (
    ErrorModel,
    ExecuteRequest,
    ExecutionRecord,
    ExecutionStatus,
    TaskResponse,
    UsageModel,
)
from app.validator import validate_against_schema

logger = logging.getLogger(__name__)

_store: dict[str, ExecutionRecord] = {}
_store_lock = Lock()
_TERMINAL = {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED}


def store_create(record: ExecutionRecord) -> None:
    with _store_lock:
        _store[record.execution_id] = record


def store_get(execution_id: str) -> Optional[ExecutionRecord]:
    with _store_lock:
        return _store.get(execution_id)


def store_update(execution_id: str, **kwargs: Any) -> None:
    """Update fields on a record. Terminal states are immutable."""
    with _store_lock:
        record = _store.get(execution_id)
        if record is None:
            return
        if record.status in _TERMINAL:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = time.time()


def store_snapshot() -> list[ExecutionRecord]:
    with _store_lock:
        return list(_store.values())


async def dispatch(record: ExecutionRecord, request: ExecuteRequest) -> None:
    """
    Background coroutine. Calls the agent and updates the store.
    Never raises — all failures are written as FAILED.
    """
    execution_id = record.execution_id

    if request.input_schema:
        result = validate_against_schema(request.input, request.input_schema, "INPUT")
        if not result.valid:
            logger.error("[%s] Input schema violation: %s", execution_id, result.error_message)
            store_update(
                execution_id,
                status=ExecutionStatus.FAILED,
                error_message=f"{result.error_code}: {result.error_message}",
                completed_at=time.time(),
            )
            return

    store_update(execution_id, status=ExecutionStatus.RUNNING, started_at=time.time())
    logger.info("[%s] Dispatching to %s at %s", execution_id, record.agent_id, record.agent_url)

    response = await _call_agent(record.agent_url, record.agent_id, request.input, record.timeout_ms)

    if response.status == "success":
        if request.output_schema and response.result is not None:
            out_result = validate_against_schema(response.result, request.output_schema, "OUTPUT")
            if not out_result.valid:
                logger.error("[%s] Output schema violation: %s", execution_id, out_result.error_message)
                store_update(
                    execution_id,
                    status=ExecutionStatus.FAILED,
                    error_message=f"{out_result.error_code}: {out_result.error_message}",
                    completed_at=time.time(),
                )
                return

        logger.info("[%s] Agent completed successfully", execution_id)
        store_update(
            execution_id,
            status=ExecutionStatus.COMPLETED,
            result=response.result,
            usage=response.usage.model_dump() if response.usage else None,
            completed_at=time.time(),
        )
    else:
        error_msg = response.error.message if response.error else "Unknown error"
        logger.error("[%s] Agent failed: %s", execution_id, error_msg)
        store_update(
            execution_id,
            status=ExecutionStatus.FAILED,
            error_message=error_msg,
            completed_at=time.time(),
        )


async def _call_agent(base_url: str, agent_id: str, payload: dict, timeout_ms: int) -> TaskResponse:
    """POST {base_url}/task with flat payload. Always returns a TaskResponse — never raises."""
    timeout_s = max(timeout_ms / 1000, 1.0)
    empty_usage = UsageModel(model_used="", input_tokens=0, output_tokens=0, latency_ms=0)

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(f"{base_url}/task", json=payload, params={"agent_id": agent_id})
    except httpx.TimeoutException:
        return TaskResponse(
            status="error",
            error=ErrorModel(code="TIMEOUT", message="Agent did not respond in time"),
            usage=empty_usage,
        )
    except httpx.ConnectError as exc:
        return TaskResponse(
            status="error",
            error=ErrorModel(code="AGENT_UNREACHABLE", message=str(exc)),
            usage=empty_usage,
        )

    if not (200 <= resp.status_code < 300):
        return TaskResponse(
            status="error",
            error=ErrorModel(code="AGENT_HTTP_ERROR", message=f"HTTP {resp.status_code}"),
            usage=empty_usage,
        )

    try:
        return TaskResponse.model_validate(resp.json())
    except Exception as exc:
        return TaskResponse(
            status="error",
            error=ErrorModel(code="INVALID_RESPONSE", message=str(exc)),
            usage=empty_usage,
        )
