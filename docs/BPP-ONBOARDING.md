# BPP Onboarding Guide

> Audience: technical lead at an AI agent provider that wants to join the
> Beckn AI Agent Marketplace.
> Time required to integrate end-to-end: 2 – 5 business days.

This document explains exactly what your BPP must do to participate in
the marketplace, what *we* (the marketplace operator) provide, and where
the responsibility line sits.

---

## 1. What is a BPP in this marketplace

In Beckn terms, a **BPP (Beckn Provider Platform)** is the network
participant that hosts the resources buyers want — in our case, **AI
agents** (summarizers, code reviewers, OCR pipelines, etc.).

You are a BPP if:
- You operate one or more AI agents you want to expose to enterprise
  buyers across the open network.
- You can run an HTTPS service that speaks Beckn v2.
- You have (or can obtain) a domain and an Ed25519 signing key for
  identity.

You bring:
- The agents themselves (you decide how they're built, hosted, scaled).
- An HTTP service that implements the Beckn v2 actions in section 4.
- An ONIX adapter instance configured with your identity.
- A catalog of `AgentFacts` documents describing each agent.

We bring:
- Identity directory (DeDi) where your subscriber id resolves to your
  endpoint URL and public key.
- The Catalog Discovery Service (CDS) where you publish your catalog
  and against which buyers search.
- The Registry where your KYC and operational status live.
- Routing infrastructure so messages flow correctly across the network.

You do **not** need to host: a Discovery Service, a Catalog Service, or
any cross-BPP infrastructure. Those are the marketplace's job.

---

## 2. Architecture at a glance

```
   BUYER SIDE                         NETWORK PLUMBING                    YOUR SIDE
                                                                          (BPP)
  ┌──────────────┐                                                     ┌──────────────┐
  │  Frontend    │                                                     │  Your BPP    │
  │  (web/app)   │                                                     │  backend     │
  └──────┬───────┘                                                     │              │
         │ HTTP                                                        │   - Webhook  │
         ▼                                                             │     handlers │
  ┌──────────────┐                  ┌──────────────┐                   │   - Catalog  │
  │     BAP      │ ───────────────► │  ONIX-BAP    │                   │     source   │
  │  backend     │ Beckn JSON       │  (signs)     │                   │   - on_publish│
  └──────────────┘                  └──────┬───────┘                   │     listener │
                                           │                           └──────┬───────┘
                                           │ routes by action                 ▲
                                           │                                  │
                                           ▼                                  │ Beckn JSON
        ┌───────────────────────────────────────────┐                 ┌──────┴───────┐
        │              CDS (us)                     │                 │  ONIX-BPP    │
        │  POST /beckn/catalog/publish              │◄────────────────┤  (yours)     │
        │  POST /beckn/discover                     │                 │  (signs)     │
        │   - validates AgentFacts                  │                 └──────────────┘
        │   - indexes with embeddings               │
        │   - serves discover queries               │
        └───────────────────────────────────────────┘
        ┌───────────────────────────────────────────┐
        │              DeDi (us)                    │   Subscriber id → endpoint URL + pubkey
        │  GET /registry/dedi/lookup/{id}/...       │   Consumed by ONIX for signature checks
        └───────────────────────────────────────────┘
        ┌───────────────────────────────────────────┐
        │              Registry (us)                │   Your KYC, status, health, jurisdiction
        │  PATCH /registry/subscribers/{id}         │
        └───────────────────────────────────────────┘
```

Everything between "BUYER SIDE" and "YOUR SIDE" is operated by the
marketplace. You only own your BPP backend, your ONIX-BPP instance, and
your catalog content.

---

## 3. Pre-flight: identity and admission

Before you can publish anything, three things must be true:

### 3.1 Subscriber id and Ed25519 keypair

- **Subscriber id**: a DNS-style identifier you control, e.g.
  `acme.ai-providers.com`. Used in `context.bppId` for every Beckn
  message you send.
- **Ed25519 keypair**: generate with any standard tool. The public key
  goes into the DeDi registry; the private key stays in your ONIX-BPP
  config.

  ```bash
  # Quick generation (any Beckn-compatible tool works):
  openssl genpkey -algorithm Ed25519 -out signing_private.pem
  openssl pkey -in signing_private.pem -pubout -out signing_public.pem
  ```

### 3.2 Registry record

Request your record via the marketplace admin or, in the MVP environment,
POST directly:

```http
POST /registry/subscribers
Content-Type: application/json

{
  "subscriber_id": "acme.ai-providers.com",
  "role": "BPP",
  "endpoint_url": "https://onix-acme.example.com/bpp/receiver",
  "backend_health_url": "https://acme.ai-providers.com",
  "public_key": "<base64 Ed25519 public key>",
  "jurisdiction": "IND",
  "organization": {
    "name": "Acme AI Providers",
    "shortDesc": "Document understanding agents"
  }
}
```

Initial status will be `active` in the MVP environment. In production
you start at `pending_kyc` and the marketplace ops team flips you to
`active` after compliance review.

### 3.3 DeDi entry

DeDi is what ONIX consults to validate signatures and route messages.
For now, ask the marketplace operator to add your subscriber id +
public key. (Self-service DeDi onboarding will become available once the
production registry stack lands.)

---

## 4. The protocol contract — actions you must implement

For each Beckn action below, you receive an HTTP POST at
`{your-bpp}/api/webhook/{action}` and you MUST:

1. Return HTTP 200 synchronously with `{"message": {"ack": {"status": "ACK"}}}`
   within 5 seconds.
2. POST the `on_*` callback to `{your-onix-bpp}/bpp/caller/on_{action}`
   when processing finishes (async; can be milliseconds or many seconds
   later).

The on_* callback must carry the same `transactionId` and `messageId`
as the inbound request, with `context.action` changed to `on_*`.

### 4.1 Required actions

| Action | What you do | Time budget |
|---|---|---|
| `select` | Resolve the requested agent, compute pricing (incl. taxes), return `on_select` with `consideration`. Reject unknown agents with `error.code = "30001"`. | < 1 s |
| `init` | Acknowledge the buyer's payment/contract terms, return `on_init` with the prepared contract. Reject unknown transactions with `error.code = "30002"`. | < 1 s |
| `confirm` | Mark the contract ACTIVE, dispatch the actual agent execution (this is YOUR business logic), return `on_confirm`. Subsequent execution result will flow through `on_status`. | < 1 s ACK; execution can be longer |
| `status` | Return the current execution state in `on_status.message.contract.performance[0]`. Code values: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`. | < 1 s |
| `cancel` | Stop execution if possible, mark contract `CLOSED`. | < 1 s |
| `on_publish` | (Inbound from CDS) acknowledge the catalog acceptance result. No callback required. | < 1 s |

### 4.2 Actions you must NOT implement

| Action | Why |
|---|---|
| `discover` | The CDS owns indexed discovery now. ONIX routing does not forward `discover` to BPPs. If you implement a handler it will simply never be called. |

### 4.3 Actions deferred (optional in MVP)

| Action | Status |
|---|---|
| `track` | Optional; only relevant for long-running streaming agents. |
| `update` | Optional; lets buyer modify a contract mid-flight. |
| `rate` / `on_rate` | Coming in Trust Framework iteration. |
| `support` / `on_support` | Recommended even in MVP; return a contact email/URL. |

### 4.4 Required HTTP surface

| Path | Method | Purpose |
|---|---|---|
| `/health` | GET | Returns `{"status": "ok"}`. Polled every 60 s by the marketplace liveness probe. |
| `/api/webhook/{action}` | POST | Inbound action handler. ONIX forwards every action here. |
| `/api/publish` (or similar) | POST | YOUR outbound publish trigger. We don't care about the path; you decide. This is what kicks off `catalog/publish` through your ONIX caller. |
| `/api/webhook/on_publish` | POST | Inbound callback from CDS reporting publish stats. |

---

## 5. The catalog contract — AgentFacts v1

Every agent you expose is described as an `AgentFacts` document. The
CDS validates each item against
[`schemas/agentfacts-v1.json`](../schemas/agentfacts-v1.json) and
rejects non-compliant publishes with `error.code = "SCHEMA_VIOLATION"`
and a per-item path.

### 5.1 Minimal valid AgentFacts payload

```json
{
  "@context": "https://raw.githubusercontent.com/i-interns/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json",
  "@type": "beckn:AIAgentService",
  "id": "acme:doc-summarizer-v1",
  "agent_name": "urn:agent:acme:DocSummarizer",
  "label": "Document Summarizer",
  "description": "Summarises legal and regulatory documents.",
  "version": "1.0.0",
  "jurisdiction": "IND",
  "provider": {
    "name": "Acme AI Providers",
    "url": "https://acme.ai-providers.com"
  },
  "endpoints": {
    "static": ["https://onix-acme.example.com/bpp/receiver"]
  },
  "capabilities": {
    "modalities": ["text"],
    "streaming": false,
    "batch": false,
    "authentication": {"methods": ["jwt"]}
  },
  "skills": [
    {
      "id": "document_summary",
      "description": "Summarises legal documents into bullet points.",
      "inputModes": ["text/plain", "application/pdf"],
      "outputModes": ["application/json"],
      "supportedLanguages": ["en", "hi"]
    }
  ],
  "sla": {"maxLatencyMs": 5000, "uptime": 0.995},
  "pricing": {"currency": "INR", "value": 6.0, "model": "per_task"}
}
```

### 5.2 Field-by-field rules

| Field | Rule | Notes |
|---|---|---|
| `@context` | string, URL | Points at the schema you conform to. |
| `@type` | string | Stable `"beckn:AIAgentService"`. |
| `id` | string | Your internal id, namespaced by org. Stable across versions of the same agent. |
| `agent_name` | URN pattern `^urn:agent:[a-z0-9-]+:[A-Za-z0-9]+$` | Stable identity of the agent across versions — this is what we key versioning on. |
| `label` | string | Human-readable name. |
| `description` | string | Prose; gets indexed into the semantic embedding. Be specific. |
| `version` | semver | New version of the same `agent_name` deprecates the previous. |
| `jurisdiction` | ISO-3166 (e.g. `IND`, `MEX`, `USA`) | Buyers can filter on this. |
| `provider` | `{name, url, did?}` | DID becomes mandatory in Trust Framework iteration. |
| `endpoints.static` | array of URLs | At least one. Typically your ONIX-BPP receiver URL. |
| `capabilities.modalities` | array | One or more of `text, audio, video, image, structured-data`. |
| `capabilities.authentication.methods` | array | E.g. `["jwt"]`, `["oauth2"]`. |
| `skills` | array, min 1 | Each skill describes a discrete task. **Skill descriptions matter for semantic search** — write them clearly. |
| `sla.maxLatencyMs` | int | Hard latency ceiling. Buyers filter on this. |
| `pricing.currency` | ISO-4217 | E.g. `INR`, `MXN`, `USD`. |
| `pricing.value` | number ≥ 0 | Base per-call cost before taxes. |
| `pricing.model` | string | Free-form (e.g. `per_call`, `per_task`, `per_token`, `subscription`, `free`). |

### 5.3 Versioning rules

- Bump `version` (semver) when behavior changes.
- The `agent_name` URN stays stable across versions.
- Publishing a new version automatically marks the previous as
  `deprecated` in our index (only the newest is returned by discover by
  default).
- The CDS keeps deprecated versions queryable by explicit version filter
  for a grace period (currently 90 days).

### 5.4 Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `on_publish.results[].errors` contains `path=$.agent_name` | URN doesn't match the pattern | Use `urn:agent:{org-lowercase}:{NameCamelCase}` |
| Skill rejected, missing `inputModes` | The required min-length-1 array is empty | Always declare at least `["text/plain"]` |
| Catalog `PARTIAL` with `path=$.skills` | Schema requires `skills` with at least one element | Add a single "general" skill if needed |
| Currency `INRR` rejected | Must be 3 characters (ISO-4217) | `INR` |
| `pricing.model` rejected | Earlier strict enum (now lifted in v1.0.1+) | Use any string from the common list |

### 5.5 Declaring rigorous input/output JSON Schemas (REQUIRED)

> **Breaking change (2026-06):** rigorous schemas are no longer optional.
> The CDS runs in **strict mode by default** — a published item without a
> non-empty `inputSchema` AND `outputSchema` is **rejected** with
> `error.code = "MISSING_SCHEMA_CONTRACT"` and never reaches the index. An
> agent that is not indexed is not discoverable. (Operators can flip the
> network to permissive mode with `STRICT_SCHEMAS=false`, in which case the
> item is indexed but flagged `pipeline_eligible=false` and excluded from
> orchestrated pipelines.)

The minimum AgentFacts contract describes only the MIME types your agent
accepts and emits (`skills[].inputModes` / `outputModes`). That is NOT
enough. You must additionally declare **two real JSON Schemas at the agent
level**, named exactly `inputSchema` and `outputSchema`:

```json
{
  "id": "acme:doc-summarizer-v1",
  "label": "Document Summarizer",
  ...
  "modelProvider": "openai",
  "inputSchema": {
    "type": "object",
    "properties": {
      "document": {"type": "string", "minLength": 1},
      "language": {"type": "string"}
    },
    "required": ["document"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "summary":    {"type": "string", "minLength": 1},
      "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 1},
      "language":   {"type": "string"}
    },
    "required": ["summary", "key_points"]
  }
}
```

> **Field naming:** the AgentFacts document you publish uses `inputSchema` /
> `outputSchema`. Some internal demo code (`services/bap/app/demo/specs.py`)
> refers to the same concept as `inputSchemaContract` / `outputSchemaContract`
> — that is a BAP-side planner detail and is **not** a valid AgentFacts field.
> Because AgentFacts v1 sets `additionalProperties: false`, publishing
> `*Contract` keys will be rejected. Publish `inputSchema` / `outputSchema`.

**What the marketplace does with these:**

1. **Admission probe** — After publish, your agent enters `probe_status =
   "probation"` and is NOT yet discoverable. The marketplace's agent probe
   synthesises a sample input from your `inputSchema`, exercises the agent,
   validates the result against your `outputSchema`, and checks latency
   against your declared SLA. Only on success is the agent promoted to
   `live` and surfaced in `discover`. A failing probe parks it as
   `failing_probe` (still hidden). See §6 for the full lifecycle.

2. **Inbound validation** — Before the orchestrator dispatches a payload to
   your agent it validates that payload against your `inputSchema`. A
   malformed payload is rejected at the marketplace boundary; you never see
   it. This is the buyer's protection.

3. **Outbound validation** — When your agent's result arrives, the
   orchestrator validates it against your `outputSchema` before surfacing it
   or chaining it into a downstream step. Drift from your declared contract
   marks the step `FAILED` with a precise error path. This is the seller's
   accountability.

**Rules:**

- Use [JSON Schema draft 2020-12](https://json-schema.org/draft/2020-12/schema).
- Both schemas must be **non-empty objects** with top-level `type: "object"`.
  An empty `{}` constrains nothing and is treated as missing (rejected).
- Every declared field must carry its declared type — **no `null` values for
  string-typed fields** (e.g. `modelProvider`). AgentFacts v1 is
  `additionalProperties: false` and strictly typed; a `null` where a string
  is expected fails validation with `SCHEMA_VIOLATION: None is not of type
  'string'` and the whole item is rejected. Omit a field rather than sending
  `null`.
- Be specific about `required` fields — every field a downstream agent might
  read must be marked `required`, otherwise the planner can't safely chain.
- Primitive-typed agents (return-a-bare-string) cannot participate in
  pipelines; wrap your result in a single-key object.
- Schemas are immutable per agent version. Bump `version` when you change them.

**Pipeline-ready example — Story 1 demo:**

The marketplace ships a worked example at `/api/demo/spec`. Two real BPPs
collaborate: Tecla (legal summarizer) → Serg (structured extractor). Both
agents publish rigorous `inputSchema` / `outputSchema`; the orchestrator
validates every hop.

---

## 6. The publish flow — getting your catalog into the index

After you have a registry record + ONIX-BPP running + at least one
AgentFacts document, the publish flow is:

```
Your BPP                 Your ONIX-BPP            CDS (us)
   │                          │                      │
   │ POST /api/publish        │                      │
   │ (you build the envelope) │                      │
   │ POST /bpp/caller/publish │                      │
   ├─────────────────────────►│                      │
   │                          │ Signs, validates     │
   │                          │ schema, routes       │
   │                          ├─────────────────────►│ /beckn/catalog/publish
   │                          │                      │ - validates AgentFacts
   │                          │                      │ - computes embeddings
   │                          │                      │ - indexes
   │                          │ ACK ◄────────────────│
   │ ACK 200 ◄────────────────│                      │
   │                          │                      │
   │                          │  (async — seconds later)
   │                          │                      │
   │ POST /api/webhook/       │                      │
   │ on_publish ◄─────────────┼──────────────────────│
   │   results: [{            │                      │
   │     catalogId, status,   │                      │
   │     stats, errors        │                      │
   │   }]                     │                      │
```

**The publish envelope you must build**: see [`services/bpp/app/routes/provider_api.py`](../services/bpp/app/routes/provider_api.py) — the `publish_catalog` function is the reference implementation. The key fields:

- `context.action`: `"catalog/publish"`
- `context.bppId`/`context.bppUri`: your subscriber id + your ONIX-BPP receiver URL
- `message.catalogs`: array of `Catalog` objects. Each catalog has `id`, `descriptor`, `provider` (required: id + descriptor), `resources` (your agents as AgentFacts), and `offers`.

**Republish frequency**: re-publish your catalog at least every 24 hours
(after that, agents start losing `freshness` score in discover). Most
operators republish on every catalog change + a daily heartbeat.

### 6.1 What happens after publish — the agent lifecycle

A published item does **not** become discoverable immediately. It moves
through a lifecycle gate:

```
publish ──► per-item validation ──► probation ──► probe ──► live  (discoverable)
              │                                       │
              │ AgentFacts invalid / missing          │ probe fails
              │ schema contract                       ▼
              ▼                                   failing_probe (hidden)
            REJECTED (not indexed)
```

1. **Per-item validation (synchronous, reported in `on_publish`)** — each
   resource is validated against AgentFacts v1 and the schema-contract rule.
   Rejections you may see in `on_publish.results[].errors[].code`:
   - `MISSING_SCHEMA_CONTRACT` — no non-empty `inputSchema`/`outputSchema` (§5.5).
   - `SCHEMA_VIOLATION` — AgentFacts shape error (e.g. a `null` where a string
     is required, an unknown field under `additionalProperties:false`).
   - `INDEX_FAILED` — internal indexing error (rare; retry).
   Accepted items are indexed with `probe_status = "probation"`.

2. **Probe (asynchronous)** — the marketplace exercises your agent with a
   synthetic input built from your `inputSchema` and validates the output
   against your `outputSchema`. Pass → `probe_status = "live"` and the agent
   appears in `discover`. Fail → `failing_probe` (hidden until a passing
   re-probe). You can trigger a re-probe with
   `POST /api/probes/{your_subscriber_id}/{agent_beckn_id}/retry`.

3. **Discoverability gate** — `discover` only returns agents that are both
   `probe_status = "live"` AND owned by an `active` subscriber. A suspended
   or pending BPP, or a probation/failing agent, is silently excluded.

So: a clean publish with valid schemas + a working agent ⇒ discoverable
within a probe cycle. A publish that is `ACCEPTED` but whose agent never
passes the probe stays invisible — check `GET /api/probes/{sub}/{agent}`.

---

## 7. Status tracking — `on_status` performance shape

When buyers call `status` while their agent is executing, your BPP
returns the current state in `contract.performance[0].status`:

```json
{
  "contract": {
    "id": "contract-abc-12345",
    "commitments": [...],
    "performance": [{
      "id": "perf-001",
      "status": {
        "code": "RUNNING",
        "name": "Running",
        "shortDesc": "Agent processing input..."
      },
      "performanceAttributes": {
        "@context": "https://.../execution-result-v1.json",
        "@type": "beckn:AgentExecution",
        "startedAt": "2026-05-22T10:00:00Z",
        "completedAt": null,
        "latencyMs": null,
        "tokensUsed": null,
        "model": null,
        "result": null,
        "status": "RUNNING"
      }
    }]
  }
}
```

Valid `status.code` values: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`.
The BAP maps these to contract states:
- `COMPLETED` → contract status becomes `COMPLETED`
- `FAILED` → contract status becomes `FAILED`
- `PENDING`/`RUNNING` → contract stays `ACTIVE`

---

## 8. Error codes you should use

| Code | When | Where |
|---|---|---|
| `30001` | Buyer selected an agent your BPP doesn't have (or one that's `inactive`) | `on_select.error` |
| `30002` | Buyer issued init/confirm/status/cancel on a transaction you never saw select for | `on_*.error` |
| `30003` | Buyer's request has an invalid field shape (e.g. missing `quantity`) | `on_*.error` |
| `30010` | Agent capacity exhausted; try again later | `on_select.error` |
| `30020` | Agent execution failed (LLM error, timeout, etc.) | `on_status.performance.status` |

Use the documented codes consistently — buyer apps and dashboards parse
on them.

---

## 9. Register with the marketplace

Once your BPP is implemented and locally testable:

1. **Run the conformance kit** (section 10) and pass all `must` tests.
2. **Submit a registry record** (POST `/registry/subscribers`).
3. **Hand off your KYC pack** (email/Slack the marketplace ops contact):
   - Company registration certificate
   - DPDP Act / GDPR compliance attestation (if jurisdiction requires)
   - Security review summary
   - Signed network participation agreement
4. **Wait for `status = active`** — the marketplace approves you after KYC.
5. **Run your first `catalog/publish`** — verify `on_publish` arrives at
   your webhook with `status: ACCEPTED`.
6. **You're live**. Buyers will find your agents via `discover` on the
   public network.

---

## 10. Conformance kit — verify before requesting admission

We provide an executable test battery you point at your BPP:

```bash
python scripts/bpp_conformance_kit.py \
  --bpp-url https://acme.ai-providers.com \
  --bpp-id acme.ai-providers.com
```

The kit runs about 15 tests covering:
- Health endpoint
- Each Beckn action returns proper ACK shape
- Unknown agent rejected with code 30001
- Unknown transaction rejected with code 30002
- Malformed payload returns NACK, not 500
- AgentFacts items in your catalog validate against the schema
- on_publish handler accepts the standard shape

Exit code 0 = ready to register. Non-zero = fix the listed issues
before you go through onboarding.

See [`scripts/bpp_conformance_kit.py`](../scripts/bpp_conformance_kit.py).

---

## 11. Reference implementation

The **`services/bpp/`** directory in this repo is a working reference
BPP that you can read top-to-bottom or fork:

- `app/routes/webhook.py` — Beckn webhook dispatcher
- `app/handlers/beckn_actions.py` — select/init/confirm/status/cancel handlers
- `app/routes/provider_api.py` — `/api/publish` builder + provider portal CRUD
- `app/db/` — PostgreSQL persistence (you can replace with anything)
- `infra/onix/bpp.yaml` — ONIX-BPP config template

This BPP is fully operational and passes the conformance kit. Treat it
as a starting point; you don't need to copy the stack (Postgres,
FastAPI) — only the protocol-facing behavior.

---

## 12. Operations expectations

| | Target |
|---|---|
| Health probe response | < 500 ms, HTTP 200 |
| ACK on inbound action | < 5 s |
| on_* callback delivery | < 30 s for fast actions, agent latency for status |
| Catalog republish frequency | At least daily |
| SLA self-reporting | Match your declared `sla.maxLatencyMs`; chronic violations affect trust score |

When you breach an SLA, the marketplace flags it. Three consecutive
breaches in a 7-day window may automatically suspend your subscriber
status. You can appeal/re-enable through ops.

---

## 13. Support and escalation

- Technical questions: `#bpp-onboarding` on the marketplace Slack
- Compliance / KYC: marketplace ops email
- Outage report: status page (URL TBD)
- Security disclosure: security@marketplace.example.com

---

## Appendix A: differences from open Beckn networks (ONDC etc.)

If you've integrated with ONDC or other Beckn networks before, the
differences in this marketplace are:

1. **AI-specific catalog schema** (AgentFacts v1) extends the base
   Beckn Resource model.
2. **Indexed discover** — there is one CDS, not gateway broadcast. You
   publish; we index.
3. **Mock DeDi during early rollout** — until the production DeDi stack
   is live, subscriber records are managed by the marketplace ops team.
4. **Per-call pricing** — typical agent transactions are micro-payments
   per request, not bulk orders.

## Appendix B: schema versioning timeline

| Version | Status | Date | Notes |
|---|---|---|---|
| AgentFacts v1.0.0 | current | 2026-04 | Initial public schema |
| AgentFacts v1.0.1 | current | 2026-05 | Pricing.model relaxed from enum to free-form string |

Backward compatibility: new versions are additive when possible. Breaking
changes get at least 60-day notice and grace period before old versions
stop validating.
