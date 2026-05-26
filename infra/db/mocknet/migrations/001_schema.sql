-- 001_schema.sql — Mock network PostgreSQL schema (Registry + CDS state).
--
-- This database is owned by the `mock-network` service. It hosts:
--   - `subscribers`:  Registry of BAPs/BPPs known to this network (Pieza 3).
--   - (later) `agent_versions`, `published_catalogs`: CDS catalog index (Pieza 1).
--
-- Note on DeDi mock vs Registry: in this MVP, DeDi (signature lookups consumed
-- by ONIX) is intentionally kept as a hardcoded dict in
-- `services/mock-network/app/dedi/data.py`. The Registry below is a separate
-- store for catalog-side onboarding metadata (admin status, KYC, health). A
-- follow-up iteration will route DeDi reads through this table so onboarding
-- a new subscriber via Registry makes it instantly resolvable by ONIX.
--
-- pgvector extension is created here because Pieza 1 (catalog publish) will
-- add vector columns to a future `agent_versions` table. Loading the extension
-- once at schema creation keeps later migrations idempotent.

CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Subscribers (Registry) ─────────────────────────────────────────
--
-- One row per network participant (BAP, BPP, or future CDS/DS instances).
-- The `subscriber_id` matches the identifier used by Beckn in context.bppId /
-- context.bapId, so the Registry and DeDi mock stay aligned by convention.
--
-- `endpoint_url` is the ONIX-side receiver URL — what other network nodes POST
-- to when they want to reach this subscriber. NOT the backend service URL.
--
-- `public_key` is the Ed25519 signing public key in base64. Stored here for
-- future "Registry as DeDi backend" mode; not consumed by ONIX in this MVP.
--
-- `status` lifecycle:
--   pending_kyc -> active -> suspended -> active (re-activated)
--                       \-> deprecated (permanently retired)
-- New subscribers default to active in MVP because there is no KYC flow yet.
--
-- `health` is updated by the liveness probe (APScheduler), not by clients.
-- `last_seen_at` is the timestamp of the most recent successful /health probe.

CREATE TABLE subscribers (
    id                      SERIAL PRIMARY KEY,
    subscriber_id           TEXT NOT NULL UNIQUE,
    role                    TEXT NOT NULL
                            CHECK (role IN ('BAP', 'BPP', 'CDS', 'DS')),
    endpoint_url            TEXT NOT NULL,
    public_key              TEXT,
    organization            JSONB NOT NULL DEFAULT '{}',
    jurisdiction            TEXT,
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('pending_kyc', 'active', 'suspended', 'deprecated')),
    health                  TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (health IN ('unknown', 'healthy', 'degraded', 'down')),
    last_seen_at            TIMESTAMPTZ,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    kyc_data                JSONB NOT NULL DEFAULT '{}',
    registered_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscribers_status ON subscribers(status);
CREATE INDEX idx_subscribers_role   ON subscribers(role);
CREATE INDEX idx_subscribers_health ON subscribers(health);

-- ─── Seed: the three identities the DeDi mock also knows ───────────
--
-- Keeps the two stores aligned without coupling them. If you add a new
-- subscriber here it must ALSO be added to services/mock-network/app/dedi/
-- data.py for ONIX signature lookups to resolve.

INSERT INTO subscribers (
    subscriber_id, role, endpoint_url, public_key, organization, jurisdiction, status, health
) VALUES
(
    'bap.example.com',
    'BAP',
    'http://onix-bap:8081/bap/receiver',
    'g/3swjI93IhZ0SScrVZapeLjU+W0AeiSid3LViYZJFo=',
    '{"name": "Demo Buyer Marketplace", "shortDesc": "Reference BAP for the AI agent marketplace"}',
    'IND',
    'active',
    'unknown'
),
(
    'bpp.example.com',
    'BPP',
    'http://onix-bpp:8082/bpp/receiver',
    'CqVy97DW45bcZPPrWIYGe2ldl9C93NFeVciiAEYsvR0=',
    '{"name": "General Tecla Industries", "shortDesc": "Demo provider of AI agents (INR pricing)"}',
    'IND',
    'active',
    'unknown'
),
(
    'bpp-serg.example.com',
    'BPP',
    'http://onix-bpp-serg:8083/bpp/receiver',
    'bfbdo3TxLzSRutUMSjl+OeDtZgqVDlCuLbR2aDbtPN0=',
    '{"name": "Serg Ops", "shortDesc": "Second demo provider of AI agents (MXN pricing)"}',
    'MEX',
    'active',
    'unknown'
);
