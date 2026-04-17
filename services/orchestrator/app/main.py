"""
Orchestrator Service — Placeholder

This service will receive task execution requests from the BPP after a
contract is confirmed, run AI agents, and return results.

Current state: placeholder with health endpoint only.
The orchestrator team is developing this service in parallel.

Integration contract with BPP:
    POST /execute
    Body: {
        "contract_id": "string",
        "agent_id": "string",
        "input": { ... task-specific payload ... }
    }
    Response: {
        "execution_id": "string",
        "status": "PENDING" | "RUNNING" | "COMPLETED" | "FAILED",
        "result": { ... agent-specific output ... },
        "metadata": {
            "startedAt": "ISO8601",
            "completedAt": "ISO8601",
            "latencyMs": int,
            "tokensConsumed": int
        }
    }

    GET /execute/{execution_id}
    Response: same as above (poll for status)

See docs/orchestrator-integration.md for full details.
"""

import os
from fastapi import FastAPI

app = FastAPI(
    title="AI Agent Orchestrator",
    version="0.1.0",
    description="Orchestrates AI agent execution for the Beckn marketplace",
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "orchestrator")


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/execute")
async def execute_task(body: dict):
    """
    Placeholder — returns a mock response.
    Replace this with real agent orchestration logic.
    """
    return {
        "execution_id": "mock-exec-001",
        "status": "COMPLETED",
        "result": {
            "summary": "[MOCK] This is a placeholder response from the orchestrator. "
            "Replace with real agent execution.",
        },
        "metadata": {
            "startedAt": "2026-04-16T00:00:00Z",
            "completedAt": "2026-04-16T00:00:01Z",
            "latencyMs": 1000,
            "tokensConsumed": 0,
        },
    }


@app.get("/execute/{execution_id}")
async def get_execution(execution_id: str):
    """Placeholder — returns mock status."""
    return {
        "execution_id": execution_id,
        "status": "COMPLETED",
        "result": {"summary": "[MOCK] Placeholder result"},
        "metadata": {},
    }
