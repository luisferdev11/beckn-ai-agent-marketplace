# Architecture — Beckn AI Agent Marketplace

> Reference document. Read this once to understand how the pieces fit.
> For task-by-task progress see [ROADMAP.md](./ROADMAP.md).

## Components and responsibilities

```
                ┌─────────────┐
                │  Frontend   │  React/Next.js — consumes BAP REST
                │   :3000     │
                └──────┬──────┘
                       │ HTTP
                       ▼
┌──────────────┐   ┌────────────┐   ┌──────────────┐
│   BAP        │──►│  ONIX-BAP  │──►│  mock-network│  (CDS + DeDi + Registry)
│   :3001      │   │  :8081     │   │   :8090      │
│              │◄──│            │◄──│              │
└──────┬───────┘   └────────────┘   └──────────────┘
       │                   ▲                ▲
       │ select/init/...   │                │ catalog/publish
       │                   │                │
       │                ┌────────────┐      │
       └───────────────►│  ONIX-BPP  │──────┘
                        │   :8082    │
                        └─────┬──────┘
                              │
                       ┌──────▼──────┐    ┌────────────┐
                       │  BPP        │───►│Orchestrator│ (placeholder)
                       │  :3002      │    │   :3003    │
                       └─────────────┘    └────────────┘
```

| Container | Port | One-liner |
|---|---|---|
| `frontend` | 3000 | React/Next.js UI; consumes BAP REST |
| `bap-marketplace` | 3001 | Buyer-side Beckn participant; exposes REST for the frontend, dispatches `discover/select/init/confirm/status/cancel` through ONIX-BAP, receives `on_*` callbacks |
| `bpp-provider` | 3002 | Reference seller-side Beckn participant ("Tecla"); maintains the catalog, handles inbound actions, dispatches `catalog/publish` |
| `bpp-serg` | 3005 | Second seller-side participant (MXN-priced demo); explicitly legacy/demo, still in-memory |
| `orchestrator` | 3003 | Receives delegated execution work from the BPP; placeholder backend that picks an agent and runs it |
| `agents` | 3004 | Individual AI agents (LLM-backed); invoked by the orchestrator |
| `mock-network` | 8090 | Single FastAPI app hosting DeDi mock, Registry, Catalog publish, Discover — see "Design principles" |
| `onix-bap`, `onix-bpp` (×2 for serg) | 8081, 8082, 8083 | ONIX adapter (Go); signs/verifies, validates schema, resolves routes via DeDi |
| `postgres-bap` | 5434 | BAP's persistence (`contracts`, `callbacks`) |
| `postgres-bpp` | 5435 | BPP's persistence (catalog + `contracts` + `executions`) |
| `postgres-mocknet` | 5436 | Mock-network's persistence (`subscribers`, `agent_versions`, `published_catalogs`) |
| `redis` | 6379 | Reserved for caching; not yet used by discover |

## Design principles

1. **Publish-subscribe over fan-out.** Discover hits one indexed CDS (`mock-network`) instead of broadcasting `discover` to every BPP at request time. Fan-out scales O(BPPs) per query, breaks under partial outages, and pins latency to the slowest responder. The CDS scales O(query) regardless of network size, because the index — built once at publish time — is queried locally.

2. **External BPPs are untouchable.** The marketplace cannot modify BPP code. We control external participants through five mechanisms only: (a) the **AgentFacts v1 schema** they must conform to; (b) the **Registry record** that gates `active` status; (c) the **liveness probe** that flags `degraded/down`; (d) the **conformance kit** they must pass to onboard; (e) **operator-side suspension** via `PATCH /registry/subscribers/{id}`.

3. **`mock-network` is the CDS.** One FastAPI service hosts the DeDi mock, the Registry, Catalog publish, and Discover. Submodules are kept isolated — they communicate only through the database, never by importing each other's services. The single thing shared in-process is the `asyncpg` pool (see `app/db/pool.py`). This keeps the boundary clean and the path to splitting them out later (each submodule has its own `routes.py` + `service.py` + `repository.py`).

4. **Schema is the contract.** AgentFacts v1 (`schemas/agentfacts-v1.json`) is enforced at publish; non-compliant items are REJECTED with `(resourceId, code, message, path)` per item. A publish with a mix of valid and invalid items returns `PARTIAL` — the valid ones are indexed, the rest are reported in `on_publish.results[].errors`. The BPP can fix and re-publish without rolling back accepted items.

5. **Beckn-compliant where it matters.** Request-path traffic goes through ONIX (signed, validated): `discover` from BAP → ONIX-BAP → CDS, `catalog/publish` from BPP → ONIX-BPP → CDS. **Callback path (`on_publish` / `on_discover`) currently bypasses ONIX** because the CDS does not yet have its own subscriber identity + Ed25519 signing key — it POSTs directly to the participant's `backend_health_url`. Documented MVP simplification; tracked in ROADMAP as Bloqueante.

## Key decisions log

| Decision | Date | Rationale | Trade-off accepted |
|---|---|---|---|
| **pgvector over Elasticsearch** | 2026-05-25 | One store, ACID with Registry, sufficient for < 1M agents. ES adds ops complexity (separate cluster, sync issues, JVM tuning). | Less sophisticated ranking primitives (no BM25 hybrid out of the box); can revisit if we hit the agent-count ceiling. |
| **`paraphrase-multilingual-MiniLM-L12-v2`** | 2026-05-25 | Multilingual Hindi/Spanish/English coverage matters for the India primary market; CPU-only inference fits our existing footprint. | Lower English-only quality than `all-mpnet-base-v2`; acceptable because recall on Hindi content matters more than peak English score. |
| **DeDi mock and Registry as two stores** | 2026-05-25 | Intentional separation in MVP. Adding a BPP today requires both entries: a Registry row (`POST /registry/subscribers`) and a `dedi/data.py` edit. This avoids the risk of breaking ONIX signature validation while we iterate on Registry shape. | Onboarding friction. Tracked as the "DeDi unification" Bloqueante item — once Registry is the source of truth for ONIX lookups, the duplication goes away. |
| **Tecla = reference, Serg = legacy demo** | 2026-05-25 | `services/bpp/` is the canonical reference implementation external integrators read/fork. Serg coexists as a second BPP for multi-provider tests but uses a transformer shim that produces non-canonical AgentFacts. | Two code paths in the demo. Documented in `services/bpp/README.md` and `memory/project_dual_bpp_arch.md`. Serg's transformer will be retired once we have a third real BPP. |
| **`on_publish`/`on_discover` bypass ONIX** | 2026-05-25 | CDS has no signing key yet. Direct HTTP keeps the callback path working end-to-end without partial trust state. | Callbacks are not signed; a malicious actor on the internal network could spoof them. Acceptable because mock-network is currently single-tenant inside our docker network. |
| **Mock BPPs are lightweight (Registry + catalog entries)** | 2026-05-25 | Matches the production posture: "real BPPs won't execute, they declare and route." Adding a mock BPP needs no extra container; just a Registry row + a published catalog. | The mock won't respond to `select/init/confirm` — fine for discover demos, not for end-to-end flows. Real partners run their own backend. |
| **Lifecycle states for subscribers** | 2026-05-25 | `pending_kyc → active → suspended → deprecated` keeps admin status orthogonal to operational `health` (`unknown/healthy/degraded/down`). | Two columns to reason about; documented in `001_schema.sql` and the BPP onboarding guide. |
| **Versioning rule: one `current` per `agent_urn`** | 2026-05-25 | Partial UNIQUE index on `agent_versions (agent_urn) WHERE status = 'current'` enforces this at the DB layer. Publishing a new version auto-deprecates the previous one inside the same transaction. | Sunset of `deprecated` rows is a roadmap item — until then, old versions accumulate. 90-day grace period documented but not yet enforced by a job. |
| **Pieza 4 (BAP LLM intent extraction) deferred** | 2026-05-25 | The espantapendejos team will hand us a curated prompt string that goes straight into `intent.textSearch`. We do not need to ship the LLM ourselves. | BAP today still falls back to `context.schemaContext` joined-by-spaces (`discover/models.py:from_envelope`). Acceptable transitional shim. |

## Module map

### `services/mock-network/app/`

| Submodule | Responsibility |
|---|---|
| `dedi/` | DeDi signature lookups. `data.py` is the hardcoded subscriber map ONIX reads; `routes.py` exposes it as `/registry/dedi/lookup/...`. |
| `registry/` | Subscriber CRUD (`routes.py`), business rules (`service.py`), DB access (`repository.py`), pydantic shapes (`models.py`), liveness probe scheduler (`liveness.py`). |
| `catalog/` | Catalog publish pipeline. `routes.py` → ACK + BackgroundTask. `service.py` → per-resource validate/embed/upsert. `validation.py` → AgentFacts validator. `repository.py` → DB writes. |
| `discover/` | Discover pipeline. `models.py` → `DiscoverQuery` shape. `query.py` → SQL hard filters + pgvector cosine. `service.py` → catalog assembly + `on_discover` dispatch. `routes.py` → ACK + BackgroundTask. |
| `embeddings/` | `EmbeddingService` (lazy-loaded `sentence-transformers`), `embed_agent(agent_facts)` for stable publish-side composition. |
| `db/pool.py` | Single `asyncpg` pool, lifespan-managed in `main.py`. |
| `main.py` | FastAPI entry point. Wires all routers, owns the pool + APScheduler lifecycle. |

### `services/bap/app/`

| Module | Responsibility |
|---|---|
| `routes/api.py` | REST surface the frontend consumes (start transaction, list contracts, etc.). |
| `routes/webhook.py` | Inbound `on_*` callback handler (`/api/bap-webhook/...`). |
| `handlers/` | Per-action callback logic (currently lean; most state writes go through `store.py`). |
| `db/repository.py` | Postgres persistence (`contracts`, `callbacks`). |
| `store.py` | In-memory cache layered on top of DB for hot paths. |

### `services/bpp/app/` — reference BPP

| Module | Responsibility |
|---|---|
| `routes/webhook.py` | Inbound `select/init/confirm/status/cancel/on_publish` (`/api/webhook/{action}`). |
| `routes/provider_api.py` | Outbound `/api/publish` → builds the Beckn envelope + provider portal CRUD. |
| `handlers/beckn_actions.py` | Per-action business logic. `handle_discover` exists but is unreachable (CDS owns discovery now). |
| `handlers/orchestrator_client.py` | Fire-and-forget call to orchestrator on `confirm`. |
| `db/repository.py` | Postgres persistence (catalog + contracts + executions). |

### `infra/db/`

| Path | Owns |
|---|---|
| `bap/migrations/001_schema.sql` | BAP-side tables (`contracts`, `callbacks`). |
| `bpp/migrations/{001,002}.sql` | BPP-side tables (`categories`, `providers`, `agents`, `contracts`, `executions`) + seed data. |
| `mocknet/migrations/{001,002,003}.sql` | mock-network tables (`subscribers`, `agent_versions`, `published_catalogs`) + pgvector extension. |

### `infra/onix/`

| File | Routes |
|---|---|
| `generic-routing-BAPCaller.yaml` | `discover` → `http://mock-network:8090/beckn` (the CDS). Other actions → BPP via DeDi. |
| `generic-routing-BPPCaller.yaml` | `catalog/publish` → `http://mock-network:8090/beckn/catalog` (the CDS). `on_*` → BAP. |
| `generic-routing-BAPReceiver.yaml` | Inbound to BAP backend. |
| `generic-routing-BPPReceiver.yaml` | Inbound to BPP backend. |
| `bap.yaml`, `bpp.yaml`, `bpp-serg.yaml` | Per-subscriber identity (Ed25519 keys, subscriber id, extendedSchema config). |

## Data model summary

### Postgres `mocknet` — three tables

**`subscribers`** (Registry source of truth)
- `subscriber_id` (UNIQUE), `role` (BAP/BPP/CDS/DS), `endpoint_url` (ONIX receiver URL), `backend_health_url` (service URL for liveness probe), `public_key` (Ed25519 base64).
- `organization` (JSONB) — `{name, shortDesc}` shown in `on_discover` provider descriptor.
- `jurisdiction`, `status` (`pending_kyc/active/suspended/deprecated`), `health` (`unknown/healthy/degraded/down`), `last_seen_at`, `consecutive_failures`, `kyc_data`.

**`agent_versions`** (Catalog index)
| Column group | Purpose |
|---|---|
| Identity: `agent_urn`, `version`, `bpp_subscriber_id`, `beckn_id`, `agentfacts_id` | Stable identity across versions; soft-FK to `subscribers`. UNIQUE `(agent_urn, version)`. |
| Denorm filters: `jurisdiction`, `languages[]`, `capability_tags[]`, `input_modes[]`, `output_modes[]`, `pricing_currency`, `pricing_value`, `sla_max_latency_ms` | Hot-path SQL filters — applied BEFORE the vector scan so HNSW walks a small subset. |
| Source of truth: `agent_facts` (JSONB) | The full AgentFacts document as received. Returned verbatim in `on_discover` `resourceAttributes`. |
| Vector: `embedding vector(384)` | pgvector cosine, HNSW index. Embedded at publish time from `text_for_agent()`. |
| Lifecycle: `status` (`current/deprecated/sunset`), `published_at`, `deprecated_at` | Partial UNIQUE on `(agent_urn) WHERE status = 'current'` guarantees one current per URN. |

**`published_catalogs`** (audit log)
- One row per `catalog/publish` POST. `transaction_id`, `message_id`, `bpp_subscriber_id`, `catalog_id`, full `raw_payload`.
- Aggregate `status` (`PENDING/ACCEPTED/REJECTED/PARTIAL`), `item_count`, `item_count_accepted`, `item_count_rejected`.
- `errors` JSONB — array of `{resourceId, code, message, path}` reported in `on_publish.results[]`.

### Postgres `bap` — two tables (unchanged in this redesign)

`contracts` (buyer POV, no FKs to BPP), `callbacks` (audit log of `on_*` received).

### Postgres `bpp` — five tables (unchanged in this redesign)

`categories`, `providers`, `agents` (AgentFacts-compatible local view), `contracts` (provider POV with local FKs), `executions` (orchestrator tracking).

## Flow diagrams

### Publish flow

```
BPP backend       ONIX-BPP          mock-network (CDS)        BPP backend
    │                │                     │                       │
    │ POST /api/     │                     │                       │
    │  publish       │                     │                       │
    ├───────────────►│ signs + validates   │                       │
    │                │ schema, routes      │                       │
    │                ├────────────────────►│ /beckn/catalog/publish│
    │                │                     │  ┌──────────────────┐│
    │                │                     │  │ validate         ││
    │                │                     │  │ AgentFacts       ││
    │                │                     │  │ embed            ││
    │                │                     │  │ upsert           ││
    │                │                     │  │ auto-deprecate   ││
    │                │                     │  │ write audit row  ││
    │                │                     │  └──────────────────┘│
    │                │ ◄── ACK (200)       │                       │
    │ ACK (200) ◄────┤                     │                       │
    │                │                     │                       │
    │                │ (async — direct HTTP, bypasses ONIX)        │
    │                │                     │                       │
    │                │                     │ POST /api/webhook/    │
    │                │                     │  on_publish           │
    │                │                     ├──────────────────────►│
    │                │                     │   results:[{          │
    │                │                     │     catalogId,        │
    │                │                     │     status,           │
    │                │                     │     stats,            │
    │                │                     │     errors }]         │
```

### Discover flow

```
BAP backend       ONIX-BAP         mock-network (CDS)        BAP backend
    │                │                     │                       │
    │ /api/discover  │                     │                       │
    ├───────────────►│ signs + validates   │                       │
    │                ├────────────────────►│ /beckn/discover       │
    │                │                     │  ┌──────────────────┐│
    │                │                     │  │ parse intent     ││
    │                │                     │  │ SQL hard filters ││
    │                │                     │  │ pgvector cosine  ││
    │                │                     │  │ group by BPP     ││
    │                │                     │  └──────────────────┘│
    │                │ ◄── ACK (200)       │                       │
    │ ACK (200) ◄────┤                     │                       │
    │                │                     │                       │
    │                │ (async — direct HTTP, bypasses ONIX)        │
    │                │                     │                       │
    │                │                     │ POST /api/bap-webhook/│
    │                │                     │  on_discover          │
    │                │                     ├──────────────────────►│
    │                │                     │   catalogs:[          │
    │                │                     │     {provider, ...    │
    │                │                     │      resources:[...]} │
    │                │                     │   ]                   │
```

### Subscriber lifecycle

```
                    POST /registry/subscribers
                              │
                              ▼
                       ┌─────────────┐
                       │ pending_kyc │  (production)
                       └──────┬──────┘
                              │ ops approves
                              ▼
                       ┌─────────────┐ ◄─────────┐
                       │   active    │           │ ops un-suspends
                       └──────┬──────┘           │
                              │ SLA breach,      │
                              │ admin suspend    │
                              ▼                  │
                       ┌─────────────┐ ──────────┘
                       │  suspended  │
                       └──────┬──────┘
                              │ DELETE (or admin retires)
                              ▼
                       ┌─────────────┐
                       │ deprecated  │  (soft-delete; idempotent)
                       └─────────────┘

Health column (orthogonal):  unknown → healthy / degraded / down
                             updated by liveness probe every 60 s
```

### Agent version lifecycle

```
        BPP publishes v1.0.0
                  │
                  ▼
           ┌─────────────┐
           │   current   │  (one per agent_urn, partial UNIQUE)
           └──────┬──────┘
                  │ BPP publishes v1.1.0 in same txn
                  ▼
           ┌─────────────┐
           │ deprecated  │  (still queryable by explicit version)
           └──────┬──────┘
                  │ 90 days (sunset job — roadmap)
                  ▼
           ┌─────────────┐
           │   sunset    │  (eligible for hard delete)
           └─────────────┘
```

## Where to find things

| If you want to... | Look at |
|---|---|
| Add a new discover filter dimension | `services/mock-network/app/discover/models.py` (StructuredFilters), `query.py` (SQL), migration if a new denorm column needed |
| Change AgentFacts validation rules | `schemas/agentfacts-v1.json` + `services/mock-network/app/catalog/validation.py` |
| Change how the embedding is composed | `services/mock-network/app/embeddings/service.py` (`text_for_agent`) |
| Add a new subscriber via API | `POST /registry/subscribers` (`services/mock-network/app/registry/routes.py`) + add to `services/mock-network/app/dedi/data.py` (until unification) |
| Adjust liveness probe policy | `services/mock-network/app/registry/liveness.py` (`PROBE_INTERVAL_SECONDS`, `DEGRADED_THRESHOLD_MS`) |
| Wire a new Beckn action | BPP: `services/bpp/app/handlers/beckn_actions.py` + `ACTION_HANDLERS` in `routes/webhook.py`. BAP: `services/bap/app/routes/webhook.py`. ONIX: routing yaml under `infra/onix/`. |
| Re-route an action at ONIX | `infra/onix/generic-routing-BAPCaller.yaml` (outbound from BAP) or `generic-routing-BPPCaller.yaml` (outbound from BPP) |
| Add a new mock subscriber for tests | `infra/db/mocknet/migrations/001_schema.sql` INSERT + `services/mock-network/app/dedi/data.py` |
| Inspect the catalog index | `GET http://mock-network:8090/cds/stats` |
| Reset everything | `docker compose down -v && docker compose up --build` |

## Glossary

| Term | Meaning |
|---|---|
| **BAP** | Beckn Application Platform. Buyer-side participant. In our marketplace: `bap-marketplace`, the "marketplace" side. |
| **BPP** | Beckn Provider Platform. Seller-side participant. Hosts the resources (AI agents). |
| **CDS** | Catalog Discovery Service. The single service that ingests catalogs (via `catalog/publish`) and serves search (via `discover`). In Beckn spec, CDS and DS are the same role. We host it as `mock-network`. |
| **DS** | Discovery Service. Same role as CDS in Beckn v2; we use "CDS" throughout. |
| **DeDi** | Decentralised Directory. The Beckn v2 registry of identities + public keys + endpoint URLs. ONIX consults DeDi to validate signatures and resolve where to POST. |
| **ONIX** | Open Network Information Exchange adapter (Go binary, `fidedocker/onix-adapter`). Sits between every participant backend and the Beckn network: signs outbound, verifies inbound, validates schema, applies routing. **Caller** = outbound (your app → network). **Receiver** = inbound (network → your app). |
| **Registry** | Mock-network table (`subscribers`) tracking each participant's admin state (KYC, status) and operational state (health). Distinct from DeDi (which is purely identity + crypto). |
| **AgentFacts** | The JSON-LD schema we enforce on each indexed agent (`schemas/agentfacts-v1.json`). Extends the base Beckn `Resource` shape with `skills`, `capabilities`, `sla`, `pricing` fields. |
| **Contract** | Beckn v2 transaction object (replaces v1 "Order"). Carries `commitments`, `consideration`, `performance`, `settlements`, `participants`. |
| **Subscriber** | A network participant identified by a DNS-style id (e.g. `bpp.example.com`). One row in `subscribers`, one entry in DeDi. |
| **`catalog/publish`** | BPP-initiated Beckn action that posts a catalog to the CDS for indexing. Returns ACK sync, on_publish async. |
| **`discover` / `on_discover`** | BAP-initiated search. ACK sync, on_discover async with one `catalog` per matching BPP. |
| **AgentFacts URN** | `urn:agent:{org}:{Name}` — stable identity across versions of an agent. Versioning key in `agent_versions`. |
