-- 005_admission_and_probes.sql — BPP & Agent registry lifecycle.
--
-- Adds the persistence layer for the full partner-BPP onboarding flow
-- (docs/PLAN-BPP-REGISTRY-LIFECYCLE.md):
--
--   admission_requests  — self-registration queue an admin reviews
--   conformance_runs    — history of the 11-test conformance kit per BPP
--   agent_probes        — synthetic execution probes per published agent
--   subscriber_audit    — append-only log of every state transition
--
-- It also extends two existing enums:
--   subscribers.status  — adds pending_admission / failing_conformance / rejected
--   subscribers.health  — adds 'unhealthy' (auto-suspend signal; liveness still
--                         writes 'down', the two coexist until Phase 5 reconciles)
--   agent_versions      — adds probe_status + last_probe_at (agent lifecycle)
--
-- Idempotent: safe to run on a fresh volume (after 001-004) and to re-apply
-- against the live DB. The agent_versions backfill runs ONLY on first column
-- creation so re-applying never wrongly promotes a genuine 'probation' agent.

-- ─── 1) Admission request queue ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS admission_requests (
    id                  SERIAL PRIMARY KEY,
    subscriber_id       TEXT NOT NULL,
    submitted_by_email  TEXT,
    organization_data   JSONB NOT NULL DEFAULT '{}',
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         TEXT,
    decision            TEXT NOT NULL DEFAULT 'pending'
                        CHECK (decision IN ('pending', 'approved', 'rejected')),
    decision_reason     TEXT
);
CREATE INDEX IF NOT EXISTS idx_admission_requests_subscriber
    ON admission_requests(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_admission_requests_decision
    ON admission_requests(decision);

-- ─── 2) Conformance kit run history ─────────────────────────────────
CREATE TABLE IF NOT EXISTS conformance_runs (
    id                  SERIAL PRIMARY KEY,
    subscriber_id       TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    total_tests         INTEGER NOT NULL DEFAULT 0,
    passed_tests        INTEGER NOT NULL DEFAULT 0,
    must_passed         BOOLEAN,
    should_passed       BOOLEAN,
    -- array of {name, criticality, passed, detail, latency_ms}
    results             JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_conformance_runs_subscriber
    ON conformance_runs(subscriber_id);

-- ─── 3) Agent probe history ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_probes (
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
CREATE INDEX IF NOT EXISTS idx_agent_probes_agent
    ON agent_probes(bpp_subscriber_id, agent_beckn_id);

-- ─── 4) Subscriber audit log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subscriber_audit (
    id              SERIAL PRIMARY KEY,
    subscriber_id   TEXT NOT NULL,
    -- admission_requested | conformance_run | approved | rejected |
    -- suspended | resumed | probe_passed | probe_failed
    action          TEXT NOT NULL,
    actor           TEXT,                 -- 'system' or admin user id
    details         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subscriber_audit_subscriber
    ON subscriber_audit(subscriber_id, occurred_at DESC);

-- ─── 5) Extend subscribers.status enum ──────────────────────────────
ALTER TABLE subscribers DROP CONSTRAINT IF EXISTS subscribers_status_check;
ALTER TABLE subscribers ADD CONSTRAINT subscribers_status_check CHECK (
    status IN (
        'pending_admission', 'pending_kyc', 'failing_conformance',
        'active', 'suspended', 'deprecated', 'rejected'
    )
);

-- ─── 6) Extend subscribers.health enum ──────────────────────────────
-- 'unhealthy' is the auto-suspend trigger (Phase 5). The liveness probe
-- currently writes 'down'; both values are permitted so Phase 5 can
-- migrate the probe without a second schema change.
ALTER TABLE subscribers DROP CONSTRAINT IF EXISTS subscribers_health_check;
ALTER TABLE subscribers ADD CONSTRAINT subscribers_health_check CHECK (
    health IN ('unknown', 'healthy', 'degraded', 'down', 'unhealthy')
);

-- ─── 7) Extend agent_versions with probation lifecycle ──────────────
-- New publishes start in 'probation' and are only surfaced in discover
-- after the agent probe promotes them to 'live' (Epic D4/E5). Agents that
-- already existed before this feature are grandfathered to 'live' so the
-- working demo catalog is not silently emptied the moment discover starts
-- filtering on probe_status. The backfill is gated on first column add to
-- stay idempotent.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agent_versions' AND column_name = 'probe_status'
    ) THEN
        ALTER TABLE agent_versions
            ADD COLUMN probe_status TEXT NOT NULL DEFAULT 'probation'
            CHECK (probe_status IN ('probation', 'live', 'failing_probe'));
        ALTER TABLE agent_versions
            ADD COLUMN last_probe_at TIMESTAMPTZ;

        UPDATE agent_versions SET probe_status = 'live';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_versions_probe_status
    ON agent_versions(probe_status);
