# AI Agents Service

Individual AI agents that perform tasks (summarization, code review, data extraction, etc.).

## Current state

**Placeholder** — the agents team is developing this service in parallel.

## How to integrate

1. Your code goes in `app/`
2. Shared Beckn models: `from beckn_models import AIAgentAttributes, AgentExecutionResult`
3. Local dev: `pip install -e ../../libs/beckn_models && pip install -r requirements.txt`
4. Full stack: `cd ../../infra && docker compose up --build`

## Integration contract with Orchestrator

The orchestrator calls your service to run a specific agent.

```
POST /task?agent_id=<agent-id>
Content-Type: application/json

{
    "text": "Content to process...",
    "language": "en"
}
```

The request body is a flat dict — no wrapper. The `agent_id` comes as a query param
so a single `/task` endpoint can dispatch to different agents.

**Response:**
```json
{
    "status": "success",
    "result": {
        "summary": "The processed output..."
    },
    "error": null,
    "usage": {
        "model_used": "llama3-70b-8192",
        "input_tokens": 400,
        "output_tokens": 120,
        "latency_ms": 3200
    }
}
```

On failure, return `"status": "error"` with an `error` object:

```json
{
    "status": "error",
    "result": null,
    "error": {
        "code": "MODEL_TIMEOUT",
        "message": "LLM did not respond within the timeout"
    },
    "usage": {
        "model_used": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0
    }
}
```

## Agent catalog

Each agent must define its capabilities using the `beckn:AIAgentService` schema.
See `libs/beckn_models/ai_agents.py` for the Pydantic model and
`schemas/ai-agents-v1.json` for the JSON schema.

The provider (BPP) publishes this info to the Beckn network.
Currently hardcoded in `services/bpp/app/catalog_data.py` — coordinate with the Beckn team when adding new agents.

## Docker

Runs on port **3004** inside `beckn_network`.
The orchestrator reaches agents at `http://agents:3004/task?agent_id=<agent-id>`.
