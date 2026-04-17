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
POST /run/<agent-id>
{
    "input": {
        "text": "Content to process...",
        "language": "en",
        "options": { ... }
    },
    "config": {
        "max_tokens": 4096,
        "temperature": 0.7
    }
}
```

**Response:**
```json
{
    "result": {
        "summary": "The processed output...",
        "confidence": 0.94
    },
    "metadata": {
        "model": "claude-sonnet-4-5-20250514",
        "tokensConsumed": 4200,
        "latencyMs": 3200
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

When ready, uncomment the `agents` service in `infra/docker-compose.yml`.
Runs on port **3004** inside `beckn_network`.
The orchestrator reaches agents at `http://agents:3004/run/<agent-id>`.
