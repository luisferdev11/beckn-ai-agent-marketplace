import os
import time
from typing import Any, Optional

import litellm
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="AI Agents Service",
    version="2.0.0",
    description="Generic LLM executor — any provider, configured from the DB",
)

START_TIME = time.time()

# Suppress litellm's verbose logging unless DEBUG
litellm.suppress_debug_info = True


# ── Response models ──────────────────────────────────────────────────────────

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


# ── Generic LLM executor ────────────────────────────────────────────────────

@app.post("/task", response_model=TaskResponse, response_model_exclude_none=True)
async def execute_task(body: dict, agent_id: str = ""):
    start_ms = time.time()

    credentials = body.pop("_credentials", {}) or {}

    # Extract prompt from multiple common field names
    prompt = (
        body.get("prompt")
        or body.get("text")
        or body.get("code")
        or ""
    )
    if not prompt:
        return TaskResponse(
            status="error",
            error=ErrorModel(code="NO_PROMPT", message='No prompt provided. Send {"prompt": "your question"}'),
            usage=UsageModel(model_used="", latency_ms=0),
        )

    # LLM config from credentials (injected by BPP from DB)
    provider = credentials.get("llm_provider", "groq")
    model = credentials.get("llm_model", "llama-3.3-70b-versatile")
    api_key = credentials.get("api_key") or os.environ.get("GROQ_API_KEY")
    system_prompt = credentials.get("system_prompt", "You are a helpful AI assistant.")
    temperature = float(credentials.get("temperature", 0.7))

    # litellm model format: "provider/model"
    litellm_model = f"{provider}/{model}" if provider else model

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await litellm.acompletion(
            model=litellm_model,
            messages=messages,
            api_key=api_key,
            temperature=temperature,
        )
    except Exception as exc:
        latency = int((time.time() - start_ms) * 1000)
        return TaskResponse(
            status="error",
            error=ErrorModel(code="LLM_ERROR", message=str(exc)),
            usage=UsageModel(model_used=litellm_model, latency_ms=latency),
        )

    latency = int((time.time() - start_ms) * 1000)
    text = response.choices[0].message.content
    usage = response.usage

    return TaskResponse(
        status="success",
        result={"text": text},
        usage=UsageModel(
            model_used=f"{provider}/{model}",
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
            latency_ms=latency,
        ),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "agents"),
        "uptime_seconds": int(time.time() - START_TIME),
        "engine": "litellm",
    }


@app.get("/metrics")
async def metrics():
    return {"engine": "litellm", "note": "per-agent metrics tracked in DB via agent_stats"}
