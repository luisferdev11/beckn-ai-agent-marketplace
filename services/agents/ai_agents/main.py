import os
import time
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from ai_agents.code_review import (
    check_model as check_code_review,
    get_metrics as get_code_review_metrics,
    run_task as run_code_review,
)
from ai_agents.summarization import (
    check_model as check_summarization,
    get_metrics as get_summarization_metrics,
    run_task as run_summarization,
)
from ai_agents.text_generation import (
    run_task as run_text_generation,
)

app = FastAPI(
    title="AI Agents Service",
    version="1.0.0",
    description="Individual AI agents for the Beckn marketplace",
)

START_TIME = time.time()


# ── Response envelope (flat result defined by each agent) ───────────────────

class ErrorModel(BaseModel):
    code: str
    message: str


class UsageModel(BaseModel):
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class TaskResponse(BaseModel):
    status: str  # "success" | "error"
    result: Optional[Any] = None
    error: Optional[ErrorModel] = None
    usage: UsageModel


# ── Agent dispatcher ─────────────────────────────────────────────────────────

_HANDLERS = {
    "agent-code-reviewer-001": run_code_review,
    # agent-summarizer-001 is the Tecla side of the Story 1 demo
    # (cross-BPP pipeline with Serg extractor-v1). Was previously
    # mis-routed to run_code_review — fixed so the published
    # outputSchema {summary, key_points, language} actually matches
    # the runtime output.
    "agent-summarizer-001": run_summarization,
    "agent-data-extractor-001": run_code_review,
    "text-generator": run_text_generation,
}

# Fallback: any unknown agent_id uses text generation
_DEFAULT_HANDLER = run_text_generation


@app.post("/task", response_model=TaskResponse, response_model_exclude_none=True)
async def execute_task(body: dict, agent_id: str = ""):
    start_time = time.time()

    handler = _HANDLERS.get(agent_id, _DEFAULT_HANDLER)

    try:
        result, usage = await handler(body)
        return TaskResponse(
            status="success", result=result,
            usage=UsageModel(latency_ms=int((time.time() - start_time) * 1000), **usage),
        )
    except Exception as exc:
        return TaskResponse(
            status="error",
            error=ErrorModel(code="EXCEPTION", message=str(exc)),
            usage=UsageModel(model_used="", latency_ms=int((time.time() - start_time) * 1000)),
        )


@app.get("/health")
async def health():
    # Both handlers hit the same Groq backend; check one and assume the
    # other follows. A single failed ping flips the whole service to
    # ``degraded`` which is what we want for the registry liveness probe.
    model_ok = await check_code_review()
    return {
        "status": "ok" if model_ok else "degraded",
        "service": os.getenv("SERVICE_NAME", "agents"),
        "uptime_seconds": int(time.time() - START_TIME),
        "agents": {
            "code_review": {"model_reachable": model_ok},
            "summarization": {"model_reachable": model_ok},
        },
    }


@app.get("/metrics")
async def metrics():
    return {
        "code_review": get_code_review_metrics(),
        "summarization": get_summarization_metrics(),
    }
