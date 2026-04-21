# Orchestrator Service

Orchestrates AI agent execution for the Beckn AI Agent Marketplace.

## Current state

**Implemented.** The orchestrator receives tasks from the BPP, calls the agents service,
and stores execution state in memory. The BPP polls `GET /execute/{id}` from `handle_status`.

## How to integrate your work

1. Clone the repo and navigate here: `cd beckn-ai-agent-marketplace/services/orchestrator/`
2. Your code goes in `app/` — `main.py` is the FastAPI entry point
3. Shared Beckn models are available: `from beckn_models import ...` (installed from `libs/beckn_models/`)
4. To run locally without Docker: `pip install -e ../../libs/beckn_models && pip install -r requirements.txt && uvicorn app.main:app --port 3003 --reload`
5. To run with the full stack: `cd ../../infra && docker compose up --build`

## Integration contract with BPP

The BPP calls the orchestrator after a Beckn `confirm` action is completed.

### Execute a task

```
POST /execute
Content-Type: application/json

{
    "contract_id": "contract-001",
    "agent_id": "agent-summarizer-001",
    "agent_url": "http://agents:3004",
    "input": {
        "text": "Document content to process..."
    },
    "timeout_ms": 30000
}
```

**Response (ACK — immediate):**
```json
{
    "execution_id": "exec-uuid",
    "status": "PENDING"
}
```

### Poll for status

```
GET /execute/{execution_id}
```

**Response:**
```json
{
    "execution_id": "exec-uuid",
    "contract_id": "contract-001",
    "agent_id": "agent-summarizer-001",
    "status": "COMPLETED",
    "result": {
        "summary": "The processed output..."
    },
    "error": null,
    "metadata": {
        "started_at": "2026-04-16T10:00:00.000Z",
        "completed_at": "2026-04-16T10:00:03.200Z",
        "latency_ms": 3200,
        "tokens_used": {
            "input": 400,
            "output": 120,
            "total": 520
        },
        "model": "llama3-70b-8192"
    }
}
```

## Architecture notes

- This service does NOT talk to Beckn/ONIX directly — only the BPP does
- For async tasks, return `status: "PENDING"` immediately and update via polling or callback
- The BPP translates your response into Beckn `on_status` performanceAttributes
- See `libs/beckn_models/ai_agents.py` for the `AgentExecutionResult` model
- See `docs/orchestrator-integration.md` for the full architecture diagram

## Docker

Runs on port **3003** inside the `beckn_network`. The BPP reaches it at `http://orchestrator:3003/execute`.
