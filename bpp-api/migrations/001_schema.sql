-- 001_schema.sql — AI Agent Marketplace schema
-- Matches the real database structure used by all handlers.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- Categories (Beckn taxonomy)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    category_id   VARCHAR(50) PRIMARY KEY,
    display_name  JSONB NOT NULL,
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE
);

-- ─────────────────────────────────────────────
-- AI Providers (BPP entities)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_providers (
    provider_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscriber_id            TEXT UNIQUE NOT NULL,
    bpp_uri                  TEXT NOT NULL,
    public_key               TEXT NOT NULL,
    organization_details     JSONB,
    trust_score_aggregate    NUMERIC(3, 2) DEFAULT 0,
    created_at               TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- AI Agents (services offered by providers)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_agents (
    agent_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id       UUID REFERENCES ai_providers(provider_id) ON DELETE CASCADE,
    category_id       VARCHAR(50) REFERENCES categories(category_id),
    access_point_url  TEXT NOT NULL,
    interaction_type  VARCHAR(20) CHECK (interaction_type IN ('sync', 'async', 'streaming')),
    protocol_type     VARCHAR(20) DEFAULT 'https',
    agent_name        JSONB NOT NULL,
    version           VARCHAR(20) NOT NULL,
    capabilities      TEXT[] NOT NULL,
    input_schema      JSONB NOT NULL,
    output_schema     JSONB NOT NULL,
    pricing_model     JSONB NOT NULL,
    status            VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'deprecated')),
    last_health_check TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agents_provider     ON ai_agents(provider_id);
CREATE INDEX IF NOT EXISTS idx_agents_category     ON ai_agents(category_id);
CREATE INDEX IF NOT EXISTS idx_agents_capabilities ON ai_agents USING GIN (capabilities);

-- ─────────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                  TEXT UNIQUE NOT NULL,
    full_name              TEXT,
    external_subscriber_id TEXT UNIQUE,
    public_key             TEXT,
    status                 VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at             TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- Transactions (consumption ledger)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                UUID REFERENCES users(user_id) ON DELETE RESTRICT,
    agent_id               UUID REFERENCES ai_agents(agent_id) ON DELETE RESTRICT,
    context_transaction_id UUID NOT NULL,
    message_id             UUID NOT NULL,
    request_payload        JSONB,
    response_payload       JSONB,
    status                 VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    amount_charged         NUMERIC(15, 6),
    currency               CHAR(3) DEFAULT 'USD',
    tokens_used            INTEGER,
    latency_ms             INTEGER,
    created_at             TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    completed_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_trans_user    ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_trans_agent   ON transactions(agent_id);
CREATE INDEX IF NOT EXISTS idx_trans_created ON transactions(created_at);
