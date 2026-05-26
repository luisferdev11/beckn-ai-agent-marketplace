import logging
import os
import time

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

from app.executor.models import ExecutionStatus
from app.executor.routes import router as executor_router
from app.executor.store import store_snapshot

app = FastAPI(
    title="AI Agent Orchestrator v2",
    version="2.0.0",
    description="Multi-agent orchestrator with LLM-guided execution plans",
)

app.include_router(executor_router)

START_TIME = time.time()


@app.get("/health")
async def health():
    snapshot = await store_snapshot()
    active = sum(1 for r in snapshot if r.status == ExecutionStatus.RUNNING)
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "orchestrator2"),
        "version": os.getenv("ORCHESTRATOR_VERSION", "2.0.0"),
        "uptime_seconds": int(time.time() - START_TIME),
        "active_executions": active,
        "total_executions": len(snapshot),
    }
