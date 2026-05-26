import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from app.executor.models import (
    ExecuteAck,
    ExecuteRequest,
    ExecuteResponse,
    ExecutionStatus,
    OrchestrationRecord,
    StepSummary,
)
from app.executor.runner import run_plan
from app.executor.store import store_create, store_get, store_snapshot

router = APIRouter(tags=["executor"])


@router.post("/execute", response_model=ExecuteAck)
async def execute_plan(request: ExecuteRequest):
    execution_id = str(uuid.uuid4())
    record = OrchestrationRecord(
        execution_id=execution_id,
        plan=request.plan,
        prompt=request.prompt,
        data=request.data,
    )
    await store_create(record)
    asyncio.create_task(run_plan(record))
    return ExecuteAck(execution_id=execution_id, status=ExecutionStatus.PENDING)


@router.get("/execute/{execution_id}", response_model=ExecuteResponse)
async def get_execution(execution_id: str):
    record = await store_get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    summary = [
        StepSummary(**s) for s in record.execution_summary
    ] if record.execution_summary else []

    return ExecuteResponse(
        execution_id=record.execution_id,
        status=record.status,
        goal=record.goal,
        result=record.result,
        execution_summary=summary,
    )


@router.get("/metrics")
async def metrics():
    snapshot = await store_snapshot()
    counts = {s.value: 0 for s in ExecutionStatus}
    for r in snapshot:
        counts[r.status.value] += 1
    return {"total": len(snapshot), **counts}
