# AI Agent Marketplace - Beckn Protocol

TO RUN :

docker compose -f docker-compose-marketplace.yml up -d --remove-orphans  
docker compose -f docker-compose-marketplace.yml ps   
docker compose -f docker-compose-marketplace.yml logs -f onix-bap onix-bpp  



An open marketplace for AI agents built on the **Beckn Protocol v2.0.0**. Providers (BPPs) publish AI agents — summarization, extraction, translation, code generation — and consumers (BAPs) discover and use them through a standardized transaction flow.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [Transaction Flow](#transaction-flow)
  - [What Each Handler Does](#what-each-handler-does)
  - [Database](#database)
- [Testing with Postman](#testing-with-postman)
- [Testing with curl](#testing-with-curl)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
                        Beckn Fabric (external, shared infrastructure)
                        ┌──────────────────────────────────────────┐
                        │  DeDi Registry — identity & routing      │
                        │  Catalog Service — stores published       │
                        │                    agent catalogs         │
                        │  Discovery Service — searches catalogs    │
                        └──────────────────────────────────────────┘
                                          ▲
                                          │
┌─────────────────────────────────────────┼──────────────────────────────────┐
│                        Docker Network (beckn_network)                      │
│                                         │                                  │
│  ┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌───────────────────┐ │
│  │ sandbox-bap │◄──►│ onix-bap │◄──►│ onix-bpp │◄──►│     bpp-api      │ │
│  │ (mock BAP)  │    │ port 8081│    │ port 8082│    │    port 3002     │ │
│  │ port 3001   │    │ signs &  │    │ signs &  │    │  Our code:       │ │
│  └─────────────┘    │ validates│    │ validates│    │  handlers, DB    │ │
│                      └──────────┘    └──────────┘    └────────┬──────────┘ │
│                                                               │            │
│  ┌───────────┐    ┌────────────────┐                          │            │
│  │   redis   │    │ postgres-beckn │◄─────────────────────────┘            │
│  │ port 6379 │    │   port 5432    │                                       │
│  └───────────┘    └────────────────┘                                       │
└────────────────────────────────────────────────────────────────────────────┘
```

**Key:** Our custom code lives exclusively in `bpp-api/`. Everything else (ONIX adapters, Redis, sandbox-bap) is shared Beckn infrastructure.

---

## Prerequisites

- **Docker** and **Docker Compose** — that's it. No Node.js, PostgreSQL, or Redis needed on your machine.
  - [Install Docker](https://docs.docker.com/engine/install/)
- **Postman** (optional) — for testing the full Beckn transaction flow.
  - [Download Postman](https://www.postman.com/downloads/)

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd starter-kit/generic-devkit/install

# 2. Start everything
docker compose -f docker-compose-marketplace.yml up --build

# 3. Verify (in another terminal)
docker compose -f docker-compose-marketplace.yml ps
```

All 6 containers should show `running` or `healthy`:

| Container | Port | Role |
|-----------|------|------|
| `postgres-beckn` | 5433 | PostgreSQL database |
| `redis` | 6379 | Shared cache for ONIX adapters |
| `onix-bap` | 8081 | BAP-side ONIX adapter (signing, validation, routing) |
| `onix-bpp` | 8082 | BPP-side ONIX adapter |
| `sandbox-bap` | 3001 | Mock BAP application (receives callbacks) |
| `bpp-api` | 3002 | Our BPP — AI Agent Marketplace API |

**Quick health check:**

```bash
curl http://localhost:3002/api/health
# {"status":"ok","service":"bpp-ai-agent-marketplace","db":"connected"}
```

**Stopping:**

```bash
# Stop containers (data persists)
docker compose -f docker-compose-marketplace.yml down

# Stop and DELETE all data
docker compose -f docker-compose-marketplace.yml down -v
```

---

## Project Structure

```
starter-kit/
├── bpp-api/                              # OUR CODE
│   ├── Dockerfile                        # Builds the bpp-api container
│   ├── package.json                      # Dependencies: express, pg, axios
│   ├── package-lock.json                 # Exact dependency versions (ensures reproducible builds)
│   ├── migrations/
│   │   ├── 001_schema.sql                # Creates tables (runs on every startup, idempotent)
│   │   └── 002_seed.sql                  # Inserts 4 sample agents (idempotent)
│   └── src/
│       ├── index.js                      # Express server, routes, webhook dispatcher
│       ├── db.js                         # PostgreSQL connection pool
│       ├── beckn.js                      # Beckn response builder + callback sender
│       ├── migrate.js                    # Runs SQL migrations on startup
│       └── handlers/
│           ├── publish.js                # Save agents to DB + publish catalog to Fabric
│           ├── discover.js               # Search agents → on_discover
│           ├── select.js                 # Agent details → on_select
│           ├── init.js                   # Create transaction → on_init
│           └── confirm.js                # Execute agent (mock LLM) → on_confirm
│
├── generic-devkit/                       # BECKN INFRASTRUCTURE (not our code)
│   ├── config/                           # ONIX adapter configuration (YAML)
│   │   ├── generic-bap.yaml             # BAP adapter: keys, plugins, registry
│   │   ├── generic-bpp.yaml             # BPP adapter: keys, plugins, registry
│   │   └── generic-routing-*.yaml       # Routing rules (where to send each action)
│   ├── install/
│   │   ├── docker-compose-marketplace.yml  # USE THIS — our full stack
│   │   ├── docker-compose-generic.yml      # Original Beckn starter (not ours)
│   │   └── docker-compose-generic-local.yml
│   └── postman/
│       ├── MarketplaceBPP.postman_collection.json  # Provider: publish agents
│       ├── MarketplaceBAP.postman_collection.json  # Consumer: discover/select/init/confirm
│       ├── BAPBecknStarterKit.postman_collection.json  # Original Beckn examples
│       └── BPPBecknStarterKit.postman_collection.json  # Original Beckn examples
│
└── README.md                             # Original Beckn starter-kit docs
```

---

## How It Works

### Transaction Flow

```
1. [Provider]  publish   → Registers agents in DB + publishes catalog to Fabric
2. [Consumer]  discover  → Searches agents via Discovery Service
3. [Consumer]  select    → Gets agent details and pricing
4. [Consumer]  init      → Creates a transaction (status: INITIALIZED)
5. [Consumer]  confirm   → Executes the agent (status: COMPLETED)
```

**publish** and **discover** involve external Fabric services.
**select**, **init**, **confirm** are fully local (BAP ↔ BPP within Docker network).

### What Each Handler Does

| Handler | Trigger | What it does | DB operation |
|---------|---------|-------------|-------------|
| `publish.js` | `POST /api/publish` | Upserts agents in DB, publishes catalog to Fabric via ONIX | Write |
| `discover.js` | webhook `discover` | Searches agents by keyword (ILIKE) | Read |
| `select.js` | webhook `select` | Returns agent details + pricing contract | Read |
| `init.js` | webhook `init` | Creates transaction record | Write |
| `confirm.js` | webhook `confirm` | Executes agent (mock LLM), updates transaction | Write |

The webhook handlers receive requests at `POST /api/webhook` routed from ONIX. They return `ACK` immediately and process asynchronously, sending `on_*` callbacks back through ONIX.

### Database

PostgreSQL runs inside Docker. On startup, `migrate.js` creates the schema and seeds sample data.

**Tables:**

| Table | Purpose |
|-------|---------|
| `categories` | Agent categories (AI-SUMMARIZATION, AI-EXTRACTION, etc.) |
| `ai_providers` | Companies that publish agents |
| `ai_agents` | The agents themselves (name, capabilities, pricing, schemas) |
| `users` | Consumers (BAP users) |
| `transactions` | Transaction lifecycle (request, response, status, cost) |

**Data persistence:**
- Data is stored in a Docker volume (`pgdata`) and survives `docker compose down`
- Data is destroyed with `docker compose down -v`
- Migrations are idempotent — safe to run repeatedly

**Seeded agents (4):**

| Agent | Category | Provider | Price |
|-------|----------|----------|-------|
| DocSummarizer Pro | AI-SUMMARIZATION | neuralspark-ai.beckn | $0.05 |
| DataExtract Engine | AI-EXTRACTION | neuralspark-ai.beckn | $0.08 |
| PolyLang Translator | AI-TRANSLATION | lingualab.beckn | $0.03 |
| CodeAssist AI | AI-CODE-GENERATION | lingualab.beckn | $0.10 |

---

## Testing with Postman

### Import collections

From `generic-devkit/postman/`, import:
- **MarketplaceBPP** — Provider actions (publish agents)
- **MarketplaceBAP** — Consumer actions (discover, select, init, confirm)

### Publish agents (Provider side)

1. Open **MarketplaceBPP** collection
2. Go to the **Variables** tab — edit your agent details
3. Click **"publish single agent"** → Send

Or use **"publish multiple agents (batch)"** to register all 4 demo agents at once.

### Run the transaction (Consumer side)

Run **MarketplaceBAP** requests in this order:
1. `discover` — find available agents
2. `select` — get details on a specific agent
3. `init` — start a transaction
4. `confirm` — execute the agent

---

## Testing with curl

```bash
# Health check
curl http://localhost:3002/api/health

# List all agents in the marketplace
curl http://localhost:3002/api/agents

# List all transactions
curl http://localhost:3002/api/transactions

# Publish a new agent
curl -X POST http://localhost:3002/api/publish \
  -H "Content-Type: application/json" \
  -d '{
  "agents": [
    {
      "category_id": "AI-SENTIMENT",
      "category_display_name": { "en": "Sentiment Analysis", "es": "Analisis de Sentimiento" },
      "provider_subscriber_id": "my-company.beckn",
      "provider_bpp_uri": "https://api.my-company.com",
      "provider_public_key": "ed25519_pub_key_placeholder",
      "agent_name": { "en": "SentimentBot Pro" },
      "access_point_url": "https://api.my-company.com/v1/sentiment",
      "interaction_type": "sync",
      "version": "1.0.0",
      "capabilities": ["sentiment", "opinion-mining", "emotion-detection"],
      "input_schema": { "type": "object", "properties": { "text": { "type": "string" } } },
      "output_schema": { "type": "object", "properties": { "sentiment": { "type": "string" }, "score": { "type": "number" } } },
      "pricing_model": { "type": "per_request", "value": 0.02, "currency": "USD" }
    }
  ]
}'
```

---

## Configuration

### Environment variables (bpp-api)

Defined in `docker-compose-marketplace.yml`. No `.env` file needed.

| Variable | Value | Description |
|----------|-------|-------------|
| `PORT` | 3002 | Server port |
| `DB_HOST` | postgres | PostgreSQL container hostname |
| `DB_PORT` | 5432 | PostgreSQL port (internal) |
| `DB_NAME` | beckn_ai_marketplace | Database name |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | PassTest12? | Database password |
| `ONIX_BPP_CALLER` | http://onix-bpp:8082/bpp/caller | ONIX callback endpoint |

### ONIX adapter configs

Located in `generic-devkit/config/`. These configure signing keys, DeDi Registry URLs, schema validation, and routing rules. Pre-configured for `beckn.one/testnet` — no changes needed to get started.

### Accessing the database directly

```bash
# From your host
docker exec -it postgres-beckn psql -U postgres -d beckn_ai_marketplace

# Example queries
SELECT agent_name->>'en' AS name, category_id, status FROM ai_agents;
SELECT * FROM transactions ORDER BY created_at DESC;
```

---

## Troubleshooting

**bpp-api won't start or crashes**
```bash
docker logs bpp-api
```
Most common cause: postgres not ready yet. The healthcheck dependency should handle this, but check if postgres-beckn is healthy.

**List agents hangs or times out**
Database connection issue. Verify postgres is running:
```bash
docker exec postgres-beckn pg_isready -U postgres
```

**publish returns 502 (partial)**
Agents were saved to DB but Fabric publish failed. Check ONIX connectivity:
```bash
docker logs onix-bpp --tail 20
```

**Port conflicts**
Default ports: 3001, 3002, 5433, 6379, 8081, 8082. If any are in use, edit `docker-compose-marketplace.yml`.

**Reset everything (fresh start)**
```bash
cd generic-devkit/install
docker compose -f docker-compose-marketplace.yml down -v
docker compose -f docker-compose-marketplace.yml up --build
```
