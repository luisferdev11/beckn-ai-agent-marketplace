# Roadmap — Discover v2 and beyond

> Snapshot of what's done, what's pending, and the recommended order.
> Updated 2026-05-25 after Piezas 1, 2, 3, 5 landed.

## Status overview

We have an end-to-end discover path: a BAP issues `discover` through ONIX-BAP,
which routes to the CDS (`mock-network`); the CDS runs hard filters + pgvector
cosine similarity against `agent_versions`, groups by BPP, and POSTs
`on_discover` to the BAP backend. Catalog publishing is symmetric — BPPs
POST `catalog/publish` through ONIX-BPP, the CDS validates AgentFacts,
embeds, and indexes, then delivers `on_publish` to the BPP backend. The
Registry (Pieza 3) owns subscriber lifecycle with a 60-second liveness probe.
The next big rock is **production-minimal hardening**: auth on Registry,
composite scoring in discover, real CDS signing keys so callbacks stop
bypassing ONIX, and the missing catalog flows (subscription, pull, retry).

## Per-service gaps

### Registry (Pieza 3 — DONE)

| What's done | What's missing | Severity |
|---|---|---|
| CRUD over subscribers (`POST/GET/PATCH/DELETE /registry/subscribers`) | No auth on any endpoint — anyone on the network can create/delete subscribers | Blocking |
| Lifecycle states (`pending_kyc → active → suspended → deprecated`) | No KYC pipeline; new subscribers auto-`active` (documented MVP simplification) | Important |
| Liveness probe (60 s `GET /health`) + `health` column + `consecutive_failures` | No audit log of admin changes (who flipped status, when, why) | Important |
| Soft-FK `bpp_subscriber_id` to `agent_versions` | No self-registration flow (today an operator inserts via API; no UI) | Important |
| `backend_health_url` separate from ONIX `endpoint_url` | DeDi mock is still a hardcoded dict in `app/dedi/data.py`; adding a BPP via Registry does NOT make it ONIX-resolvable | Blocking |
| Seeds for `bap.example.com`, `bpp.example.com`, `bpp-serg.example.com` | No suspension automation (SLA breach → auto-suspend) | Polish |

### Catalog publish + index (Pieza 1 — DONE)

| What's done | What's missing | Severity |
|---|---|---|
| `POST /beckn/catalog/publish` returns ACK sync + processes in BackgroundTasks | No `catalog/subscription` flow — BAPs cannot subscribe to delta pushes | Important |
| AgentFacts validation (per-item `ItemError` with code/message/path) | No `catalog/pull` — BAPs cannot bootstrap from a fresh index | Important |
| Per-resource embed → `agent_versions` upsert with auto-deprecation of prior `current` | No retry queue for failed `on_publish` callbacks — single best-effort POST | Important |
| `published_catalogs` audit log with PENDING/ACCEPTED/REJECTED/PARTIAL aggregate | No sunset job for `deprecated` rows (grace period documented as 90 days, not enforced) | Important |
| `on_publish` delivery to BPP backend (bypasses ONIX — documented) | No per-BPP quota / rate limit on publish frequency | Polish |
| Operator endpoint `GET /cds/stats` exposing `current_agents_total` | Stats endpoint is single metric; no per-BPP, per-jurisdiction, per-status breakdown | Polish |

### Discover (Pieza 2 — DONE)

| What's done | What's missing | Severity |
|---|---|---|
| Two-stage pipeline: SQL hard filters → pgvector cosine, ORDER BY similarity, published_at | Composite scoring (`semantic × 0.6 + freshness × 0.2 + health × 0.2`) — only `similarity` is exposed today | Blocking |
| Structured `intent.filters`: jurisdiction, languages, capabilities, currency, max_price_value, max_latency_ms | RFC 9535 JSONPath subset — spec mandates JSONPath; we only accept a flat dict | Important |
| `text_search` precedence: `intent.textSearch` → `context.schemaContext` (BAP back-compat) | No spatial / geographic filtering (no lat/lon, no service region polygons) | Important |
| Catalog grouping: one `catalog` per BPP, provider descriptor pulled from Registry | No result caching — every discover re-embeds and re-scans (single hot agent query is fast, fan-out from many BAPs will not be) | Important |
| `on_discover` delivery to BAP backend (bypasses ONIX — documented) | No feedback loop (which results were clicked/selected → re-rank signal) | Important |
| `limit` (1–100), default 20 | No pagination cursor / offset — discover always returns the top-N | Polish |

### Cross-cutting (applies to all three)

| What's done | What's missing | Severity |
|---|---|---|
| Single `asyncpg` pool shared across submodules in `mock-network` | No auth/JWT/bearer on any `mock-network` endpoint (Registry, CDS operator, catalog ops) | Blocking |
| Structured `logger.info` per request with txn-id prefix | No structured JSON logs, no OpenTelemetry tracing (ONIX has `otelSetup` plugin available but unused) | Important |
| Postgres volumes (`pgdata-mocknet`, `pgdata-bap`, `pgdata-bpp`) | No automated backups; no point-in-time recovery; no DR plan | Important |
| Frontend (`services/frontend/`) consumes BAP REST API | Frontend does not yet render the multi-catalog `on_discover` shape (one catalog per BPP); UX assumes flat list | Important |
| `pytest` per service (unit + contract + integration) + `tests/e2e/` for Docker | CI not wired to enforce on PR; no coverage gate | Important |
| `docs/BPP-ONBOARDING.md` covers external integrator path | No BAP-side onboarding doc; no operator runbook for Registry suspension/restoration | Polish |
| `docs/dev-to-production.md` lists prod-hardening items | TLS to Postgres (`sslmode=require`) and secrets-out-of-`.env` tracked in `docs/tech-debt-db-architecture.md`, not yet done | Important |

## Prioritized roadmap

### Bloqueante for production-minimal

- **Auth on `mock-network`** — bearer or Beckn-sig on Registry CRUD and CDS operator endpoints. ~2 d.
- **Composite discover scoring** — pull `health` + `published_at` into ORDER BY, expose `score` in the response; needs a JOIN on `subscribers` and a small SQL refactor. ~2 d.
- **DeDi unification** — Registry rows become the source for ONIX signature lookups (eliminate `dedi/data.py` static dict). Without this, onboarding via Registry is half-complete. ~3 d.
- **CDS signing key + ONIX callback path** — give the CDS its own subscriber id + Ed25519 key so `on_publish` / `on_discover` route through ONIX instead of direct HTTP. ~3 d.
- **TLS + secret management** — `sslmode=require` BAP/BPP/mock-net → Postgres; secrets out of `infra/.env`. ~2 d.

### Importante but not blocking

- **`catalog/subscription` + `catalog/pull`** — BAPs need delta push / bootstrap pull. ~4 d.
- **`on_publish` retry queue** — at-least-once delivery with backoff. ~2 d.
- **JSONPath subset for `intent.filters`** — at minimum `$.skills[*].supportedLanguages` style for nested filters. ~3 d.
- **Spatial filtering** — `service_region` polygon on `agent_versions`, PostGIS `&&` with intent. ~3 d.
- **Discover caching** — Redis cache keyed by `(query_vec_hash, filters)` with short TTL. ~2 d.
- **Feedback loop** — `select` events feed back into a signal column used in scoring. ~3 d.
- **Sunset job for deprecated agents** — APScheduler job that deletes `deprecated` rows older than 90 days. ~1 d.
- **Audit log for Registry admin changes** — new table `subscriber_audit`. ~1 d.
- **Self-registration UI** — provider portal endpoint that calls `POST /registry/subscribers`. ~3 d.
- **Per-BPP publish quotas** — rate limit `catalog/publish` per `bppId`. ~1 d.
- **Frontend update for multi-catalog `on_discover`** — group results by provider. ~2 d.
- **Structured JSON logging + OpenTelemetry** — wire ONIX `otelSetup`, add OTel exporter to all FastAPI services. ~3 d.
- **CI: run all pytest tiers on PR** — GitHub Actions, fail on red. ~1 d.
- **Postgres backup automation** — pg_basebackup + WAL archiving per DB. ~2 d.

### Polish

- **Per-BPP / per-jurisdiction breakdown in `GET /cds/stats`**. ~0.5 d.
- **Discover pagination cursor**. ~1 d.
- **KYC pipeline state machine** — actual checks for the `pending_kyc → active` transition. ~5 d.
- **Operator runbook** — Registry suspension/restoration playbook, on-call basics. ~1 d.
- **BAP-side onboarding doc** — mirror of `BPP-ONBOARDING.md` for buyer integrators. ~1 d.

## Out-of-scope or deferred

| Item | Rationale |
|---|---|
| Pieza 4 — BAP LLM intent extraction | espantapendejos team will supply a curated prompt string that maps directly to `intent.textSearch`; we do not need to ship the LLM ourselves |
| Full RFC 9535 JSONPath | Subset is enough for every story currently on the board; full grammar adds parser complexity for marginal value |
| Multi-region / geo-replicated CDS | Single CDS in one region is fine until traffic forces it; premature optimisation |
| Trust score requiring historical data | Needs months of `select`/`rate` data we do not yet have |
| Elasticsearch index | pgvector + HNSW is sufficient < 1M agents; one less store to operate |
| Per-call streaming (`track`) | Only relevant for streaming agents; no BPP on the network ships one yet |
| Production-grade DeDi (signed entries, replication) | DeDi-as-Registry table covers the MVP; productionising the DeDi protocol itself is a separate large effort |

## Known bugs (parked)

Tracked in the team's bug list at 2026-05-21 (`memory/project_pending_bugs_post_transfer.md`).
Listed here for visibility; pick up after the blocking roadmap items.

| Severity | Summary | Documented in |
|---|---|---|
| Blocking | Conformance kit malformed-JSON case currently returns 500 not NACK | `docs/BPP-ONBOARDING.md` §10 footnote |
| Blocking | BAP init/confirm still has hardcoded fallbacks if `on_select` not yet stored | `docs/dev-to-production.md` §8 |
| Important | `bpp-serg` in-memory contracts (no postgres yet) — desync with `bpp-provider` | `docs/dev-to-production.md` §3 footer + CLAUDE.md Pendiente |
| Important | `extendedSchema_enabled: false` on all ONIX endpoints — re-enable once schema hosted | `docs/dev-to-production.md` §2 |
| Important | Catalog publish at the production CDS strips `resourceAttributes` due to schema host | `docs/dev-to-production.md` §5 |
| Important | `discover` handler still present in `services/bpp/app/handlers/beckn_actions.py` (unreachable but should be removed) | `services/bpp/README.md` §"must NOT copy" |
| Important | Serg catalog transformer is an explicit demo shim — produces non-canonical AgentFacts | `memory/project_dual_bpp_arch.md` |
| Polish | `bppId` hardcoded in `services/bap/app/config.py` — cannot talk to multiple BPPs without code change | `docs/dev-to-production.md` §8 |
| Polish | `_derive_probe_url` fallback in `liveness.py` is best-effort — fails for some endpoint shapes | inline TODO |
| Polish | `cds/stats` returns a single integer — no per-BPP breakdown | `app/catalog/routes.py` operator_router |

## Next sprint candidates

| Work item | Effort | Impact | Blocking? |
|---|---|---|---|
| Composite discover scoring (similarity + freshness + health) | ~2 d | High — directly improves discover quality on every query | Yes |
| Auth on `mock-network` endpoints (Registry + CDS operator) | ~2 d | High — closes the obvious security hole before any external pilot | Yes |
| DeDi unification (Registry rows feed ONIX lookups) | ~3 d | High — onboarding a new BPP becomes one API call instead of two repos | Yes |
| CI: pytest tiers on PR | ~1 d | Medium — protects the next 6 months of refactors | No |
