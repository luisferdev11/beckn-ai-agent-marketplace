"""
AI Agents Service — Placeholder

Individual AI agents that perform tasks. The orchestrator calls
POST /run/<agent-id> to execute a specific agent.

Current state: placeholder with mock responses.
The agents team is developing this service in parallel.
"""

import os
from fastapi import FastAPI

app = FastAPI(
    title="AI Agents Service",
    version="0.1.0",
    description="Individual AI agents for the Beckn marketplace",
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "agents")


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/run/{agent_id}")
async def run_agent(agent_id: str, body: dict):
    """Placeholder — returns a mock response."""
    return {
        "result": {
            "summary": f"[MOCK] Response from agent {agent_id}. Replace with real implementation.",
        },
        "metadata": {
            "model": "mock",
            "tokensConsumed": 0,
            "latencyMs": 100,
        },
    }
