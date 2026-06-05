import asyncio
import dataclasses
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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


# ── Debug serialization ──────────────────────────────────────────────────────

def _serialize_record(record: OrchestrationRecord) -> dict:
    """Serialize a full OrchestrationRecord to a JSON-safe dict."""
    completed = {}
    for sid, cs in record.completed_steps.items():
        completed[sid] = dataclasses.asdict(cs)

    errors = [dataclasses.asdict(e) for e in record.error_log]
    conversation = [dataclasses.asdict(c) for c in record.conversation_log]

    return {
        "execution_id": record.execution_id,
        "status": record.status.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "goal": record.goal,
        "prompt": record.prompt,
        "data": record.data,
        "plan": record.plan,
        "execution_brief": record.execution_brief,
        "current_state": record.current_state.value,
        "current_layer": record.current_layer,
        "step_statuses": {k: v.value for k, v in record.step_statuses.items()},
        "completed_steps": completed,
        "pending_steps": record.pending_steps,
        "error_log": errors,
        "conversation_log": conversation,
        "result": record.result,
        "execution_summary": record.execution_summary,
    }


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


# ── Debug endpoints (full record with error_log, conversation_log) ───────────

@router.get("/debug/executions")
async def debug_list_executions():
    """List all executions with full internal state for debugging."""
    snapshot = await store_snapshot()
    # Return newest first, with a summary to keep the list response light
    items = []
    for r in sorted(snapshot, key=lambda x: x.created_at, reverse=True):
        items.append({
            "execution_id": r.execution_id,
            "status": r.status.value,
            "goal": r.goal,
            "current_state": r.current_state.value,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "step_statuses": {k: v.value for k, v in r.step_statuses.items()},
            "error_count": len(r.error_log),
            "conversation_count": len(r.conversation_log),
        })
    return JSONResponse(content=items, headers={"Access-Control-Allow-Origin": "*"})


@router.get("/debug/executions/{execution_id}")
async def debug_get_execution(execution_id: str):
    """Full execution record including error_log, conversation_log, plan, data."""
    record = await store_get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return JSONResponse(content=_serialize_record(record), headers={"Access-Control-Allow-Origin": "*"})
