# BPP & Agent Registry — Full Lifecycle Implementation Plan

> **Document version:** 2026-06-01
> **Status:** approved by user, ready for implementation
> **Branch convention:** start from `develop`, create `feat/registry-lifecycle-phase-N`

## What this document is

Concrete plan to implement end-to-end onboarding for partner BPPs to our
marketplace: from self-registration, through conformance verification,
admin approval, agent publication with rigorous schemas, agent probing
to verify the agent actually works, and continuous health monitoring
with auto-suspension. Includes phased delivery, per-epic acceptance
criteria, data-model changes, and explicit non-goals.

If you are a fresh Claude session picking up this work, **read § "How
to onboard a new session" at the bottom first** — it has the repo
conventions, what's already done, what's in flight by other teams, and
what you must NOT touch to avoid merge conflicts.

---

## 1. The conceptual flow

```
                          ┌─ external BPP operator ─┐
                          │                         │
                          ▼                         │
        ┌─────────────────────────────────┐         │
   1.   │  POST /admission-requests       │         │
        │  status: pending_admission      │         │
        └──────────────┬──────────────────┘         │
                       │                            │
                       ▼                            │
        ┌─────────────────────────────────┐         │
   2.   │  Conformance Kit (auto)         │         │
        │  11 tests against BPP webhook   │         │
        │  Persisted in conformance_runs  │         │
        └──────────────┬──────────────────┘         │
                       │ pass must (9 tests)?       │
              ┌────────┴────────┐                   │
              │ NO              │ YES               │
              ▼                 ▼                   │
        stays pending     ┌──────────────────┐      │
        BPP fixes,        │ admin approves   │      │
        re-runs ─────────►│ status: active   │      │
                          └────────┬─────────┘      │
                                   ▼                │
        ┌─────────────────────────────────┐         │
   3.   │  Liveness probe starts (60s)    │         │
        │  health=healthy|degraded|...    │         │
        └─────────────────────────────────┘         │
                                                    │
        ┌─ BPP operator publishes agents ───────────┘
        ▼
        ┌─────────────────────────────────┐
   4.   │  Provider portal UI: AgentFacts │
        │  with inputSchemaContract +     │
        │  outputSchemaContract required  │
        └──────────────┬──────────────────┘
                       ▼
        ┌─────────────────────────────────┐
   5.   │  /beckn/catalog/publish to CDS  │
        │  CDS validates AgentFacts shape │
        │  agent.probe_status='probation' │
        └──────────────┬──────────────────┘
                       ▼
        ┌─────────────────────────────────┐
   6.   │  Agent Probe (NEW)              │
        │  synthetic input from schema    │
        │  output validated vs schema     │
        │  latency <= declared SLA?       │
        └──────────────┬──────────────────┘
                       │ pass?
              ┌────────┴────────┐
              │ NO              │ YES
              ▼                 ▼
        failing_probe      probe_status='live'
        excluded from      surfaced in
        discover           discover
                                │
                                ▼
        ┌─────────────────────────────────┐
   7.   │  Continuous health monitoring   │
        │  3 fails → degraded             │
        │  10 fails → unhealthy →         │
        │    auto-suspend BPP             │
        │  Recovery → un-suspend          │
        └─────────────────────────────────┘
```

## 2. Components — existing vs new

| Component | Today | What we do |
|---|---|---|
| Registry CRUD | ✅ 5 endpoints `POST/GET/PATCH/DELETE /registry/subscribers` (`services/mock-network/app/registry/routes.py`) | EXTEND — add admission queue endpoints |
| Lifecycle states | ✅ `pending_kyc → active → suspended → deprecated` | EXTEND — add `pending_admission`, `failing_conformance`, `rejected` |
| Liveness probe (BPP /health) | ✅ Every 60s, updates `subscribers.health`, `consecutive_failures` (`services/mock-network/app/registry/liveness.py`) | EXTEND — add auto-suspend policy when consecutive_failures crosses threshold |
| Conformance kit | ✅ 11 tests, CLI-only (`scripts/bpp_conformance_kit.py`) | REFACTOR — expose as `app/conformance/` callable module; CLI becomes a wrapper |
| CDS catalog publish | ✅ Validates AgentFacts v1, indexes with embeddings (`services/mock-network/app/catalog/`) | TIGHTEN — require `inputSchemaContract` and `outputSchemaContract` per item (strict mode) |
| BPP provider API (Tecla) | ✅ CRUD agents/providers in `/api/agents` (`services/bpp/app/routes/provider_api.py`) | REFERENCE — pattern for partner BPPs; don't break |
| Publisher frontend page | ⚠️ Exists at `services/frontend/src/app/dashboard/publisher/page.tsx` (179 lines, calls `/api/publisher/agents`) | EXTEND — full AgentFacts form including new schema fields |
| Admin dashboard | ⚠️ Exists at `services/frontend/src/app/dashboard/admin/page.tsx` | EXTEND — admission queue tile + conformance report + audit timeline |
| **Admission requests queue** | ❌ Doesn't exist | NEW — table + endpoints + admin review flow |
| **Conformance runs persistence** | ❌ Kit runs only ad-hoc | NEW — auto-trigger from Registry + persist results |
| **Agent probe service** | ❌ Doesn't exist | NEW — module in mock-network + cron + dedicated table |
| **Audit log of state changes** | ❌ Doesn't exist | NEW — `subscriber_audit` + `agent_audit` tables |

## 3. Data model changes

One new migration: `infra/db/mocknet/migrations/005_admission_and_probes.sql`.

```sql
-- 1) Admission request queue
CREATE TABLE admission_requests (
    id                  SERIAL PRIMARY KEY,
    subscriber_id       TEXT NOT NULL,
    submitted_by_email  TEXT,
    organization_data   JSONB NOT NULL,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         TEXT,
    decision            TEXT NOT NULL DEFAULT 'pending'
                        CHECK (decision IN ('pending','approved','rejected')),
    decision_reason     TEXT
);
CREATE INDEX idx_admission_requests_subscriber ON admission_requests(subscriber_id);
CREATE INDEX idx_admission_requests_decision   ON admission_requests(decision);

-- 2) Conformance kit run history
CREATE TABLE conformance_runs (
    id                  SERIAL PRIMARY KEY,
    subscriber_id       TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    total_tests         INTEGER NOT NULL DEFAULT 0,
    passed_tests        INTEGER NOT NULL DEFAULT 0,
    must_passed         BOOLEAN,
    should_passed       BOOLEAN,
    results             JSONB NOT NULL DEFAULT '[]'   -- array of {name, criticality, passed, error?}
);
CREATE INDEX idx_conformance_runs_subscriber ON conformance_runs(subscriber_id);

-- 3) Agent probe history
CREATE TABLE agent_probes (
    id                  SERIAL PRIMARY KEY,
    bpp_subscriber_id   TEXT NOT NULL,
    agent_beckn_id      TEXT NOT NULL,
    agent_version       TEXT NOT NULL,
    probed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_payload       JSONB,
    output_payload      JSONB,
    input_valid         BOOLEAN,
    output_valid        BOOLEAN,
    latency_ms          INTEGER,
    latency_within_sla  BOOLEAN,
    passed              BOOLEAN NOT NULL,
    failure_reason      TEXT
);
CREATE INDEX idx_agent_probes_agent ON agent_probes(bpp_subscriber_id, agent_beckn_id);

-- 4) Subscriber audit log
CREATE TABLE subscriber_audit (
    id              SERIAL PRIMARY KEY,
    subscriber_id   TEXT NOT NULL,
    action          TEXT NOT NULL,        -- admission_requested|conformance_run|approved|rejected|suspended|resumed
    actor           TEXT,                 -- 'system' or admin user id
    details         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriber_audit_subscriber ON subscriber_audit(subscriber_id, occurred_at DESC);

-- 5) Extend subscribers.status enum (drop + recreate CHECK)
ALTER TABLE subscribers DROP CONSTRAINT IF EXISTS subscribers_status_check;
ALTER TABLE subscribers ADD CONSTRAINT subscribers_status_check CHECK (
    status IN (
        'pending_admission','pending_kyc','failing_conformance',
        'active','suspended','deprecated','rejected'
    )
);

-- 6) Extend agent_versions with probation lifecycle
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS probe_status TEXT
    NOT NULL DEFAULT 'probation'
    CHECK (probe_status IN ('probation','live','failing_probe'));
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS last_probe_at TIMESTAMPTZ;
```

**Critical:** discover query (`services/mock-network/app/discover/query.py`) must
filter `WHERE av.probe_status = 'live' AND s.status = 'active'`. Failing
that filter, probation agents and suspended BPPs leak into the catalog.

## 4. Acceptance criteria per epic

### Epic A — BPP self-registration

| AC | Verification |
|---|---|
| A1. External BPP `POST /registry/admission-requests` with `{subscriber_id, endpoint_url, public_key, organization, jurisdiction, contact_email}` returns 202 + request_id | curl test: status 202, row in `admission_requests` |
| A2. System creates `subscribers` row with `status='pending_admission'` (not discoverable) | discover does NOT return that BPP's agents |
| A3. Validation: 409 if `subscriber_id` exists; 422 if `public_key` not valid Ed25519 base64 | curl with duplicate → 409, malformed key → 422 |
| A4. Audit log row written with `action='admission_requested'` | DB query confirms row |

### Epic B — Conformance gate

| AC | Verification |
|---|---|
| B1. Conformance kit refactored to `services/mock-network/app/conformance/` callable module; CLI still works | Old CLI still passes against running BPP; `from app.conformance import run_for_bpp` works |
| B2. On admission request, Registry auto-triggers conformance kit in background task against the declared endpoint | Logs show kit running; row in `conformance_runs` within seconds |
| B3. Each of 11 tests persisted with `criticality` (must/should), pass/fail, error message | `SELECT results FROM conformance_runs` shows full per-test detail |
| B4. BPP can re-trigger via `POST /registry/admission-requests/{id}/retry-conformance` | New row, new attempt |
| B5. `subscribers.status='active'` requires `must_passed=true` (9 must tests); 2 should can fail with warning | Test: must failing → admin cannot approve → 422 |
| B6. UI component `<ConformanceReport />` renders pass/fail per test with criticality | Visible in admin dashboard |

### Epic C — Admin approval

| AC | Verification |
|---|---|
| C1. Admin (role `admin` JWT claim) sees queue of `pending_admission` in `/dashboard/admin` | Tile shows N pending + list |
| C2. Admin can drill into a request: organization, jurisdiction, contact, latest conformance result | Drawer/modal shows full info |
| C3. Admin approves → `subscribers.status='active'`, request `decision='approved'`, audit log; BPP discoverable within next liveness cycle | DB transitions + appears in discover ~60s |
| C4. Admin rejects with reason → `subscribers.status='rejected'`, `decision='rejected'`, BPP not discoverable, audit log | DB + absence in discover |

### Epic D — Agent publication (existing + tightened)

| AC | Verification |
|---|---|
| D1. CDS rejects publish without `inputSchemaContract` AND `outputSchemaContract` per item (strict mode, default ON) | curl publish without schemas → `error.code='MISSING_SCHEMA_CONTRACT'`, item rejected |
| D2. Permissive mode (env var `STRICT_SCHEMAS=false`) allows publish without schemas — agent gets `pipeline_eligible=false` field | env flag flip works |
| D3. Publisher portal UI: textarea with JSON validation client-side for both schemas | Form rejects malformed JSON before submit |
| D4. New agent inserted with `agent_versions.probe_status='probation'`; not surfaced in discover yet | DB + discover empty for that beckn_id |

### Epic E — Agent probe

| AC | Verification |
|---|---|
| E1. Probe synthesizes a valid payload from `inputSchemaContract` (uses `jsonschema` defaults + minimal example) | Probe sends a payload that passes `jsonschema.validate(input_schema)` |
| E2. Probe executes full Beckn flow: select → init → confirm → status loop | Trace in `agent_probes.input_payload`, `output_payload` |
| E3. Output validated against `outputSchemaContract` — flag stored in `output_valid` | DB column reflects boolean |
| E4. Latency measured; flag `latency_within_sla = (measured <= 2 * declared_sla)` | DB column populated |
| E5. Probe passes (all 3 flags true) → `agent_versions.probe_status='live'`; surfaced in discover | Discover query returns the agent |
| E6. Probe fails → `probe_status='failing_probe'`; agent excluded from discover; audit log | Discover excludes; audit row written |
| E7. BPP can `POST /api/probes/{agent_id}/retry` to re-run probe | New `agent_probes` row, status may flip |

### Epic F — Liveness + auto-suspend

| AC | Verification |
|---|---|
| F1. Existing 60s liveness probe keeps working (no regression) | `subscribers.last_seen_at` advances |
| F2. 3 consecutive failures → `health='degraded'` (already works) | Stop BPP container, wait 3 min → `degraded` |
| F3. 10 consecutive failures → `health='unhealthy'` AND `subscribers.status='suspended'` auto | BPP off 10+ min → status flips |
| F4. Suspended BPP: all its agents excluded from discover | Discover query filter respected |
| F5. Recovery (3 healthy probes after unhealthy) → status flips to `active`; agents back in discover | BPP back online → automatic recovery |
| F6. Admin can force `unsuspend` via dashboard button | Click → patch → discover restored |

### Epic G — Audit + observability

| AC | Verification |
|---|---|
| G1. Every state transition (admission, conformance, approval, probe, suspend, recovery) writes to `subscriber_audit` | DB shows full history |
| G2. Admin UI shows BPP timeline (what happened when) | Timeline component renders |
| G3. Structured logs with `subscriber_id` and `correlation_id` for traceability | grep finds traces |

## 5. Phased delivery

| Phase | Scope | Effort | Demo-able |
|---|---|---|---|
| **Phase 1 — Backend foundation** | Migration `005_admission_and_probes.sql` + admission queue endpoints + conformance refactor + persistence + auto-trigger on admission | ~6-8h | Curl + DB inspection |
| **Phase 2 — Strict schemas + publisher form** | CDS strict mode for schemas + frontend publisher form with JSON validation | ~4-6h | UI usable |
| **Phase 3 — Agent probe** | Probe module + cron + persistence + discover filter | ~6-8h | Agent registration end-to-end |
| **Phase 4 — Admin UI** | Admission queue + conformance report + agent probe results + timeline | ~6-8h | Demo complete |
| **Phase 5 — Auto-suspend + recovery** | Liveness extension + consequential cron | ~3-4h | Resilience demo |

**Total: ~25-35h**. Recommend Phases 1 + 2 in one session (~10-12h, all
backend + a bit of UI), checkpoint, then Phase 3, then 4 + 5.

## 6. Risks and non-goals

| Risk | Mitigation |
|---|---|
| Conflict with planner team (working on planner → orchestrator2 integration) | Do NOT touch `services/orchestrator*`, `services/planner`, `services/bap/app/demo/`. Only Registry, CDS, conformance kit, frontend dashboards (admin + publisher) |
| Conflict with frontend planner wiring (search page) | Work only on `/dashboard/admin` and `/dashboard/publisher` pages. Do NOT touch `/search` or `/dashboard/demo` |
| Probe consumes LLM tokens | Document as cost-of-admission; rate-limit to 1 probe per agent per minute |
| Conformance refactor breaks CLI | Keep CLI as a wrapper over the new module (back-compat) |

**Non-goals for this initiative:**
- DID/VC real (mock-trust stays)
- Self-service KYC pipeline (admin manual approval is fine)
- Probes with partner-supplied test data (synthetic only)
- Email notifications to BPPs (out of scope)

---

## How to onboard a new Claude session

If you are a fresh Claude reading this, here is everything you need
before starting to implement.

### Repo conventions

- **Communication in Spanish** with the user. Code and comments in English.
- **TDD-first.** Write the failing test, then make it pass. Project has 4
  test layers: `services/*/tests/unit/`, `.../tests/contract/`,
  `.../tests/integration/`, `tests/e2e/`.
- **No Co-Authored-By Claude** in commit messages (saved as user preference).
- **Phases of the briefing are a ceiling, not a target.** Ship as fast as
  possible; "advancing beyond Phase 4" is welcome.
- **One PR per coherent change.** Don't bundle unrelated work.

### Repo layout (only what's relevant here)

```
beckn-ai-agent-marketplace/
├── services/
│   ├── bap/                       # BAP buyer side (:3001) — has demo orchestrator
│   ├── bpp/                       # Tecla BPP (:3002) — reference impl
│   ├── bpp-serg/                  # Serg BPP (:3005) — in-memory
│   ├── mock-network/              # CDS + Registry + DeDi (:8090)  ← MAIN FOCUS
│   │   └── app/
│   │       ├── catalog/           # publish + index + AgentFacts validation
│   │       ├── discover/          # composite scoring + retrieval
│   │       ├── registry/          # subscribers CRUD + liveness probe
│   │       │   ├── routes.py
│   │       │   ├── repository.py
│   │       │   └── liveness.py    # 60s health probe
│   │       └── ratings/           # rating aggregator
│   ├── agents/                    # Tecla agents runtime (:3004) — DON'T TOUCH
│   ├── agents-serg/               # Serg agents runtime (:3006) — DON'T TOUCH
│   ├── orchestrator/              # v1 single-agent — DON'T TOUCH
│   ├── orchestrator2/             # v2 multi-agent — TEAM IS WORKING ON IT, DON'T TOUCH
│   ├── planner/                   # 2-phase planner (:3010) — TEAM IS WORKING ON IT
│   └── frontend/                  # Next.js (:3000)
│       └── src/app/dashboard/
│           ├── admin/page.tsx     ← OK to extend
│           ├── publisher/page.tsx ← OK to extend
│           ├── consumer/page.tsx  ← AVOID
│           ├── demo/page.tsx      ← DON'T TOUCH (other team)
│           └── ...
├── infra/
│   ├── docker-compose.yml
│   └── db/{bap,bpp,mocknet}/migrations/
├── scripts/
│   └── bpp_conformance_kit.py     ← refactor INTO mock-network module
└── docs/
    ├── BPP-ONBOARDING.md          ← partner-facing spec (already has §5.5 about schemas)
    ├── ROADMAP.md
    └── PLAN-BPP-REGISTRY-LIFECYCLE.md  ← this document
```

### Currently merged work (don't redo)

- **PR #40** — cancel CLOSED + malformed JSON NACK + composite discover scoring (semantic/freshness/health)
- **PR #41** — rate / on_rate end-to-end + quality scoring as 4th component
- **PR #42** — planner two-phase (BAP `/api/plan`)
- **PR #43** — multi-BPP routing fix (`bpp_id`/`bpp_uri` forwarded by frontend)
- **PR #44** — frontend score breakdown + rate UI
- **PR #45** — test stale fixes (closed parked bug #5)
- **PR #46** — frontend planner wiring
- **PR #47** — Story 1 cross-BPP demo orchestrator (`services/bap/app/demo/`)

The team is currently working on integrating the planner with
orchestrator2 (the demo will be replaced by that integration). **Stay
out of those paths.**

### Test running

Tests run inside Docker containers. The project uses Python 3.12; the
host has 3.9. Pattern that works:

```bash
# 1. Install pytest deps (idempotent)
docker exec infra-<service>-1 pip install -q pytest pytest-asyncio respx httpx

# 2. Copy tests + pytest.ini into the container
docker exec infra-<service>-1 rm -rf /app/tests
docker cp services/<service>/tests infra-<service>-1:/app/tests
docker cp services/<service>/pytest.ini infra-<service>-1:/app/pytest.ini

# 3. Run
docker exec infra-<service>-1 python -m pytest tests/ -q --tb=line
```

Apply migrations to live DBs:
```bash
cat infra/db/mocknet/migrations/005_admission_and_probes.sql \
  | docker exec -i infra-postgres-mocknet-1 psql -U mocknet_user -d mocknet_db
```

Rebuild a single service after code change:
```bash
cd infra && docker compose up -d --build --no-deps <service-name>
```

### Live verification commands

```bash
# Stack health
docker ps --format '{{.Names}}\t{{.Status}}' | grep infra-

# mock-network healthy
curl -sf http://localhost:8090/health

# Existing registry CRUD still works
curl -s http://localhost:8090/registry/subscribers | python3 -m json.tool | head -30

# Full happy-path smoke (don't break this)
python scripts/smoke_test_dual_bpp.py
# Expect: ALL GREEN — dual-BPP marketplace is working end-to-end

# Demo orchestrator (don't break this either)
curl -s http://localhost:3001/api/demo/spec | python3 -m json.tool | head
```

### Memory system (where to learn project context)

Read first:
```
/home/pillofon/.claude-infosys/projects/-home-pillofon-Documents-infosys-Agent-Beckn-Marketplace/memory/MEMORY.md
```

Especially relevant for this work:
- `project_marketplace.md`
- `reference_beckn_v2_schema_quirks.md` — schema asymmetries that bite
- `project_dual_bpp_arch.md` — hard-won rules about dual-BPP
- `project_external_bpp_strategy.md` — the 5-layer strategy this plan operationalizes
- `feedback_ship_asap_over_phases.md` — user prefers shipping fast

### Beckn v2 reminders

- This is **v2 only**. If something talks about `search` / `Order` / `Gateway`,
  it's v1, ignore.
- Use `discover` not `search`, `Contract` not `Order`, `rate` not `rating`.
- JSON-LD with `@context` and `@type`.
- Spec at `protocol-specifications-v2/api/v2.0.0/beckn.yaml`.

### Where to start (Phase 1, in order)

1. Create branch `feat/registry-lifecycle-phase-1` off `develop`.
2. Write migration `infra/db/mocknet/migrations/005_admission_and_probes.sql`
   per § 3 above. Apply to live DB (don't restart volumes).
3. Create `services/mock-network/app/admission/` module:
   - `models.py` (Pydantic AdmissionRequest)
   - `repository.py` (CRUD on `admission_requests` + `subscriber_audit`)
   - `routes.py` (`POST /registry/admission-requests`,
     `GET /registry/admission-requests`,
     `POST /registry/admission-requests/{id}/approve|reject|retry-conformance`)
   - Register in `services/mock-network/app/main.py`
4. Refactor `scripts/bpp_conformance_kit.py` into
   `services/mock-network/app/conformance/` callable module:
   - `runner.py` exposing `async def run_for_bpp(subscriber_id) -> ConformanceRun`
   - Keep `scripts/bpp_conformance_kit.py` as a thin CLI wrapper
   - Tests: refactor without breaking the existing CLI behavior
5. Wire auto-trigger: on `POST /registry/admission-requests`, spawn a
   background task that runs the kit and writes to `conformance_runs`.
6. TDD: unit tests for the state machine; integration tests for the
   endpoints (use the existing `fake_subscribers` autouse fixture in
   `services/mock-network/tests/conftest.py`).
7. Rebuild mock-network container, verify with curl, write a smoke
   script `scripts/smoke_admission_flow.py`.

### What to do when you get stuck

- Check `git log --oneline -20` to see recent merges
- Run `gh pr list --state open --limit 10` to see what's in flight
- The user uses `/btw` and `/loop` slash commands; respect interruptions
- If something seems wrong, ask the user before destructive actions
  (deleting branches, force pushing, dropping tables)

### Communication style with the user

- Direct, concrete. Reports of what changed + what's next.
- Show real data (logs, test output) not descriptions
- Tables for status, bullets for actions
- Don't over-explain when the user is technical (they are)
- When proposing options, use the `AskUserQuestion` tool with 2-4 clear options

---

**Ready signal:** if you can verify the existing smoke
(`scripts/smoke_test_dual_bpp.py`) is ALL GREEN, the existing registry
endpoints work, and the admin dashboard renders, you're set. Start
Phase 1 with the migration.
