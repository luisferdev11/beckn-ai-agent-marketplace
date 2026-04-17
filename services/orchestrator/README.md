# Orchestrator Service

Orchestrates AI agent execution for the Beckn AI Agent Marketplace.

## Current state

**Placeholder** — returns mock responses. The orchestrator team is developing
this service in parallel.

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
    "input": {
        "text": "Document content to process...",
        "language": "en"
    }
}
```

**Response:**
```json
{
    "execution_id": "exec-uuid",
    "status": "PENDING | RUNNING | COMPLETED | FAILED",
    "result": {
        "summary": "The processed output..."
    },
    "metadata": {
        "startedAt": "2026-04-16T10:00:00Z",
        "completedAt": "2026-04-16T10:00:03Z",
        "latencyMs": 3200,
        "tokensConsumed": 4200
    }
}
```

### Poll for status

```
GET /execute/{execution_id}
```

Returns same response shape as above.

## Architecture notes

- This service does NOT talk to Beckn/ONIX directly — only the BPP does
- For async tasks, return `status: "PENDING"` immediately and update via polling or callback
- The BPP translates your response into Beckn `on_status` performanceAttributes
- See `libs/beckn_models/ai_agents.py` for the `AgentExecutionResult` model
- See `docs/orchestrator-integration.md` for the full architecture diagram

## Docker

Runs on port **3003** inside the `beckn_network`. The BPP reaches it at `http://orchestrator:3003/execute`.
