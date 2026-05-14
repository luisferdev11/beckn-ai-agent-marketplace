import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app import executor
from app.models import (
    ExecuteAck,
    ExecuteRequest,
    ExecuteResponse,
    ExecutionMetadata,
    ExecutionRecord,
    ExecutionStatus,
    TokensUsed,
)

app = FastAPI(
    title="AI Agent Orchestrator",
    version="1.0.0",
    description="Orchestrates AI agent execution for the Beckn marketplace",
)

START_TIME = time.time()


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _record_to_response(record: ExecutionRecord) -> ExecuteResponse:
    tokens_used = None
    model = None
    if record.usage:
        inp = record.usage.get("input_tokens", 0)
        out = record.usage.get("output_tokens", 0)
        tokens_used = TokensUsed(input=inp, output=out, total=inp + out)
        model = record.usage.get("model_used") or None

    latency_ms = None
    if record.started_at and record.completed_at:
        latency_ms = int((record.completed_at - record.started_at) * 1000)

    return ExecuteResponse(
        execution_id=record.execution_id,
        contract_id=record.contract_id,
        agent_id=record.agent_id,
        status=record.status,
        result=record.result,
        error=record.error_message,
        metadata=ExecutionMetadata(
            started_at=_iso(record.started_at),
            completed_at=_iso(record.completed_at),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            model=model,
        ),
    )


@app.post("/execute", response_model=ExecuteAck)
async def execute_task(request: ExecuteRequest):
    execution_id = str(uuid.uuid4())
    record = ExecutionRecord(
        execution_id=execution_id,
        contract_id=request.contract_id,
        agent_id=request.agent_id,
        agent_url=request.agent_url,
        input=request.input,
        input_schema=request.input_schema,
        output_schema=request.output_schema,
        timeout_ms=request.timeout_ms,
    )
    executor.store_create(record)
    asyncio.create_task(executor.dispatch(record, request))
    return ExecuteAck(execution_id=execution_id, status=ExecutionStatus.PENDING)


@app.get("/execute/{execution_id}", response_model=ExecuteResponse)
async def get_execution(execution_id: str):
    record = executor.store_get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return _record_to_response(record)


@app.get("/health")
async def health():
    snapshot = executor.store_snapshot()
    active = sum(1 for r in snapshot if r.status == ExecutionStatus.RUNNING)
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "orchestrator"),
        "version": os.getenv("ORCHESTRATOR_VERSION", "1.0.0"),
        "uptime_seconds": int(time.time() - START_TIME),
        "active_executions": active,
        "total_executions": len(snapshot),
    }


@app.get("/metrics")
async def metrics():
    snapshot = executor.store_snapshot()
    counts = {s.value: 0 for s in ExecutionStatus}
    for r in snapshot:
        counts[r.status.value] += 1
    return {"total": len(snapshot), **counts}
