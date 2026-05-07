"""
Agent Catalog API — FastAPI entry point.
Includes: agent execution, SLA monitoring, quality scoring, pipeline routing.

Two execution surfaces:
  - POST /run        — native OrderedApi shape (debug, internal use, pipelines)
  - POST /task?agent_id=X
                     — orchestrator-compatible shape: body is the raw payload
                       and the response matches the orchestrator's TaskResponse
                       envelope (status / result / usage / error). Used by
                       the orchestrator service in this repo.
"""

import time
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from registry import REGISTRY
from metrics.store  import counter_inc, gauge_inc, gauge_dec, histogram_observe, generate_metrics_text
from sla.monitor      import check_transaction, get_violations, get_stats
from quality.score  import run_benchmarks, get_latest_scores, get_score_history
from pipeline.router import run_pipeline
from core.llm import GROQ_MODEL


# ── Pydantic models ────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    agent_id:        str
    task_type:       str
    payload:         dict
    timeout_seconds: Optional[float] = 30.0


class AgentRunResponse(BaseModel):
    agent_id:         str
    task_type:        str
    status:           str
    result:           Optional[str] = None
    latency_ms:       float
    token_count:      int
    error:            Optional[str] = None
    sla_violations:   list          = []


class PipelineRequest(BaseModel):
    steps: list[dict]   # each step: {agent_id, task_type, payload}


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agent Catalog API — Serg Ops",
    description="Agent catalog with SLA monitoring, quality scoring, and pipeline routing",
    version="6.0.0",
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": "agents-serg", "agents": list(REGISTRY.keys())}


# ── Core agent execution ───────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {
        "status": "ok",
        "agents": {aid: list(tasks.keys()) for aid, tasks in REGISTRY.items()},
    }


@app.get("/agents", tags=["catalog"])
def list_agents():
    return {aid: list(tasks.keys()) for aid, tasks in REGISTRY.items()}


@app.post("/run", response_model=AgentRunResponse, tags=["execution"])
def run_agent(req: AgentRunRequest):
    """Execute a single agent task. SLA is checked automatically."""
    agent_id  = req.agent_id
    task_type = req.task_type
    status    = "success"
    result    = None
    tokens    = 0
    error_msg = None

    if agent_id not in REGISTRY:
        raise HTTPException(404, f"Agent '{agent_id}' not found. Available: {list(REGISTRY)}")

    agent_tasks = REGISTRY[agent_id]
    if task_type not in agent_tasks:
        raise HTTPException(404, f"Task '{task_type}' not in '{agent_id}'. Available: {list(agent_tasks)}")

    agent      = agent_tasks[task_type]
    run_labels = {"agent_id": agent_id, "task_type": task_type}

    gauge_inc("agent_active_tasks", run_labels)
    start = time.perf_counter()

    try:
        result, tokens = agent.run(req.payload)
    except Exception as exc:
        status    = "failure"
        error_msg = str(exc)
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        gauge_dec("agent_active_tasks", run_labels)

        labels = {"agent_id": agent_id, "task_type": task_type, "status": status}
        counter_inc("agent_transactions_total", labels)
        counter_inc("agent_token_count_total",  labels, tokens)
        histogram_observe("agent_latency_ms",   labels, elapsed_ms)

    # ── SLA check ──────────────────────────────────────────────────────────────
    violations = check_transaction(agent_id, task_type, elapsed_ms, status)

    return AgentRunResponse(
        agent_id       = agent_id,
        task_type      = task_type,
        status         = status,
        result         = result,
        latency_ms     = round(elapsed_ms, 2),
        token_count    = tokens,
        error          = error_msg,
        sla_violations = violations,
    )


# ── Orchestrator-compatible /task endpoint ────────────────────────────────────
#
# The orchestrator calls POST {agent_url}/task?agent_id=X with the raw payload
# as body. The response envelope is fixed:
#   { status: "success"|"error", result, error?: {code,message}, usage: {...} }


def _resolve_task_type(agent_id: str) -> str:
    """Each registered agent currently exposes exactly one task_type."""
    tasks = REGISTRY[agent_id]
    return next(iter(tasks.keys()))


@app.post("/task", tags=["execution"])
async def task(agent_id: str, request: Request):
    """
    Orchestrator-compatible execution endpoint.

    Query params:  agent_id (required)
    Body:          the raw payload dict the agent expects (e.g. {"text": "..."})
    """
    if agent_id not in REGISTRY:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": {"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' not in catalog"},
                "usage": {"model_used": GROQ_MODEL, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0},
            },
        )

    payload = await request.json()
    task_type = _resolve_task_type(agent_id)
    agent = REGISTRY[agent_id][task_type]

    labels = {"agent_id": agent_id, "task_type": task_type}
    gauge_inc("agent_active_tasks", labels)
    start = time.perf_counter()
    status = "success"
    result_text: Optional[str] = None
    tokens = 0
    error_payload: Optional[dict] = None

    try:
        result_text, tokens = agent.run(payload)
    except ValueError as exc:
        status = "error"
        error_payload = {"code": "INVALID_INPUT", "message": str(exc)}
    except RuntimeError as exc:
        status = "error"
        error_payload = {"code": "UPSTREAM_ERROR", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error_payload = {"code": "AGENT_FAILURE", "message": str(exc)}
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        gauge_dec("agent_active_tasks", labels)
        rec_labels = {**labels, "status": "success" if status == "success" else "failure"}
        counter_inc("agent_transactions_total", rec_labels)
        counter_inc("agent_token_count_total",  rec_labels, tokens)
        histogram_observe("agent_latency_ms",   rec_labels, elapsed_ms)

    check_transaction(agent_id, task_type, elapsed_ms, "success" if status == "success" else "failure")

    body = {
        "status": status,
        "result": result_text,
        "usage": {
            "model_used": GROQ_MODEL,
            "input_tokens": 0,         # Groq returns total only; split is best-effort
            "output_tokens": tokens,
            "latency_ms": int(elapsed_ms),
        },
    }
    if error_payload:
        body["error"] = error_payload
    return body


# ── Pipeline ───────────────────────────────────────────────────────────────────

@app.post("/run/pipeline", tags=["execution"])
def run_pipeline_endpoint(req: PipelineRequest):
    """
    Execute multiple agents in sequence.
    Each step's output is automatically passed as input to the next step.

    Example body:
    {
      "steps": [
        {"agent_id": "extractor-v1",  "task_type": "extract",    "payload": {"text": "John joined on Jan 5", "extract": "names, dates"}},
        {"agent_id": "translator-v1", "task_type": "translate",   "payload": {}}
      ]
    }
    """
    if not req.steps:
        raise HTTPException(400, "Pipeline must have at least one step")

    return run_pipeline(req.steps, REGISTRY)


# ── SLA ────────────────────────────────────────────────────────────────────────

@app.get("/sla/violations", tags=["sla"])
def sla_violations(agent_id: str = None, severity: str = None):
    """
    Return all recorded SLA violations.
    Filter by agent_id or severity (WARNING / CRITICAL).
    """
    return {
        "violations": get_violations(agent_id=agent_id, severity=severity),
        "count":      len(get_violations(agent_id=agent_id, severity=severity)),
    }


@app.get("/sla/stats", tags=["sla"])
def sla_stats():
    """Return current failure rates and SLA status per agent."""
    return get_stats()


# ── Quality ────────────────────────────────────────────────────────────────────

@app.post("/quality/run", tags=["quality"])
def run_quality_benchmarks(background_tasks: BackgroundTasks):
    """
    Trigger a quality benchmark run against all agents.
    Runs in the background so the request returns immediately.
    Results available at GET /quality/scores after completion.
    """
    def _run():
        run_benchmarks(REGISTRY)

    background_tasks.add_task(_run)
    return {"message": "Benchmark run started. Check /quality/scores in a few seconds."}


@app.post("/quality/run/sync", tags=["quality"])
def run_quality_benchmarks_sync():
    """
    Run quality benchmarks synchronously and return results immediately.
    Warning: this will take several seconds as it calls the LLM for each test.
    """
    return run_benchmarks(REGISTRY)


@app.get("/quality/scores", tags=["quality"])
def quality_scores(agent_id: str = None):
    """Return the latest quality scores. Filter by agent_id if provided."""
    scores = get_latest_scores()
    if agent_id:
        return scores.get(agent_id, {"message": f"No scores yet for {agent_id}"})
    return scores


@app.get("/quality/history", tags=["quality"])
def quality_history(agent_id: str = None):
    """Return the full score history over time."""
    return {"history": get_score_history(agent_id=agent_id)}


# ── Prometheus metrics ─────────────────────────────────────────────────────────

@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
def metrics():
    return PlainTextResponse(generate_metrics_text(), media_type="text/plain; version=0.0.4")


@app.post("/metrics/record", tags=["observability"])
def record_metric(event: dict):
    labels = {"agent_id": event["agent_id"], "task_type": event["task_type"], "status": event["status"]}
    counter_inc("agent_transactions_total", labels)
    counter_inc("agent_token_count_total",  labels, event.get("token_count", 0))
    histogram_observe("agent_latency_ms",   labels, event.get("latency_ms", 0))
    return {"recorded": True}
