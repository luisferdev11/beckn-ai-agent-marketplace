# services/bpp — Reference BPP Implementation

> **This directory is the canonical reference implementation of a BPP
> for the Beckn AI Agent Marketplace.**
>
> External providers integrating with the marketplace can read this code
> top-to-bottom to understand the contract, or fork it as a starting
> point. The protocol-facing behavior is what matters; you do NOT need
> to copy the storage stack (Postgres, FastAPI) — only the HTTP shapes
> and the action flow.

## Status as a reference

| Aspect | This BPP shows | Production BPPs MUST |
|---|---|---|
| HTTP webhook surface | `app/routes/webhook.py` | Match the path layout `/api/webhook/{action}` |
| Beckn action handlers | `app/handlers/beckn_actions.py` | Implement select/init/confirm/status/cancel; return Beckn ACK envelope |
| Catalog as AgentFacts | `app/routes/provider_api.py:_agent_to_beckn_resource` | Produce AgentFacts v1 documents — see `schemas/agentfacts-v1.json` |
| catalog/publish flow | `app/routes/provider_api.py:publish_catalog` | Build the Beckn envelope, route through ONIX-BPP caller |
| on_publish handler | `app/routes/webhook.py:on_publish branch` | Accept the callback shape, log results |
| Error codes | `app/handlers/beckn_actions.py:UNKNOWN_AGENT_CODE / TXN_NOT_FOUND_CODE` | Use `30001` and `30002` for the standard rejection cases |
| Liveness | `/health` endpoint | Respond < 500 ms with HTTP 200 |
| Storage | PostgreSQL with asyncpg | Pick whatever you like — the protocol doesn't care |

## What you can copy verbatim

- The shape of `_agent_to_beckn_resource` — it's the cleanest example
  of producing an AgentFacts-compliant resource from any source-of-truth.
- The `build_response_context` helper in `app/handlers/beckn_actions.py`
  — every BPP needs the same self-identify-on-callback pattern.
- The `_txn_not_found_response` and `_unknown_agent_response` helpers —
  both demonstrate the canonical error envelope shape.

## What is local-only (your BPP will look different)

- The PostgreSQL schema and the `app/db/repository.py` layer. Use any
  storage. Replace this whole subtree.
- The provider portal CRUD (`POST /api/agents`, etc.) — that's a UI
  convenience for our demo; your provider portal is your business.
- The `AGENT_URL_MAP` env var that the orchestrator uses. Real BPPs
  control their own agent runtimes and decide internally how to route
  to them.

## What you must NOT copy

- The legacy in-memory contract behavior (it's been removed; just make
  sure your storage actually persists).
- The `discover` handler (`handle_discover` in `beckn_actions.py`).
  Discovery is now owned by the CDS at `mock-network`. The handler
  remains in the file for historical reference only and is unreachable
  from `ACTION_HANDLERS`.

## Verifying conformance

Run the conformance kit against your BPP before requesting admission:

```bash
python scripts/bpp_conformance_kit.py \
  --bpp-url http://your-bpp-host:3002 \
  --bpp-id your-subscriber.example.com
```

Tecla itself passes the kit's `must` tests (with one known non-critical
gap on malformed-JSON handling — see [`docs/BPP-ONBOARDING.md`](../../docs/BPP-ONBOARDING.md)).

## Reading order

If you're new to this codebase, read in this order:

1. `app/main.py` — FastAPI entry point.
2. `app/routes/webhook.py` — how inbound Beckn actions are dispatched.
3. `app/handlers/beckn_actions.py` — the actual per-action logic.
4. `app/routes/provider_api.py` — outbound flows (`/api/publish`) +
   provider portal CRUD.
5. `app/db/repository.py` — storage layer (skip if you'll use your own).
6. `schemas/agentfacts-v1.json` (in repo root `schemas/`) — the catalog
   contract you must conform to.
