-- 001_schema.sql
-- Schema for beckn_catalog DB (frontend: providers, categories, agents, agent_stats)
--
-- Both catalogPool (DB_NAME_CATALOG) and metricsPool (DB_NAME_METRICS) point to
-- this same database so that LEFT JOIN agent_stats in single-pool queries works.

CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS providers (
    id               SERIAL PRIMARY KEY,
    subscriber_id    VARCHAR(200) NOT NULL UNIQUE,
    bpp_uri          TEXT NOT NULL,
    organization     JSONB NOT NULL DEFAULT '{}',
    status           VARCHAR(20) NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'inactive', 'pending')),
    integration_mode VARCHAR(50) DEFAULT 'onix',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agents (
    id                SERIAL PRIMARY KEY,
    provider_id       INTEGER NOT NULL REFERENCES providers(id),
    category_id       INTEGER REFERENCES categories(id),
    beckn_id          VARCHAR(200) NOT NULL UNIQUE,
    agent_name        JSONB NOT NULL DEFAULT '{}',
    label             VARCHAR(200),
    description       TEXT,
    version           VARCHAR(20) DEFAULT '1.0.0',
    status            VARCHAR(20) NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'inactive', 'deprecated')),
    pricing_model     JSONB NOT NULL DEFAULT '{}',
    access_point_url  TEXT,
    resource_attributes JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- agent_stats lives in the same DB so catalog-pool queries can JOIN it directly.
-- metricsPool is also pointed at this DB (DB_NAME_METRICS=beckn_catalog).
CREATE TABLE IF NOT EXISTS agent_stats (
    agent_id      INTEGER PRIMARY KEY REFERENCES agents(id),
    total_queries INTEGER NOT NULL DEFAULT 0,
    unique_users  INTEGER NOT NULL DEFAULT 0,
    week_queries  INTEGER NOT NULL DEFAULT 0,
    last_used_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agents_provider ON agents(provider_id);
CREATE INDEX IF NOT EXISTS idx_agents_status   ON agents(status);
