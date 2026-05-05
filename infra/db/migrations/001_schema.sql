-- 001_schema.sql — Beckn AI Agent Marketplace PostgreSQL schema
-- All primary keys use SERIAL (auto-incrementing integers)

-- ─── Categories ─────────────────────────────────────────────
CREATE TABLE categories (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    display_name    JSONB NOT NULL DEFAULT '{}',
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Providers ──────────────────────────────────────────────
CREATE TABLE providers (
    id              SERIAL PRIMARY KEY,
    subscriber_id   TEXT NOT NULL UNIQUE,
    bpp_uri         TEXT NOT NULL,
    public_key      TEXT,
    organization    JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Agents (AgentFacts-compatible) ─────────────────────────
CREATE TABLE agents (
    id                  SERIAL PRIMARY KEY,
    provider_id         INTEGER NOT NULL REFERENCES providers(id),
    category_id         INTEGER NOT NULL REFERENCES categories(id),
    agent_name          JSONB NOT NULL DEFAULT '{}',
    description         TEXT,
    version             VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    access_point_url    TEXT,
    interaction_type    VARCHAR(20) NOT NULL DEFAULT 'sync'
                        CHECK (interaction_type IN ('sync', 'async', 'streaming')),
    capabilities        JSONB NOT NULL DEFAULT '[]',
    skills              JSONB NOT NULL DEFAULT '[]',
    input_schema        JSONB NOT NULL DEFAULT '{}',
    output_schema       JSONB NOT NULL DEFAULT '{}',
    pricing_model       JSONB NOT NULL DEFAULT '{}',
    sla                 JSONB NOT NULL DEFAULT '{}',
    jurisdiction        VARCHAR(10),
    endpoints           JSONB NOT NULL DEFAULT '{"static": []}',
    modalities          JSONB NOT NULL DEFAULT '["text"]',
    authentication      JSONB NOT NULL DEFAULT '{"methods": ["jwt"]}',
    status              VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive', 'deprecated')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agents_provider ON agents(provider_id);
CREATE INDEX idx_agents_category ON agents(category_id);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_capabilities ON agents USING GIN (capabilities);
CREATE INDEX idx_agents_skills ON agents USING GIN (skills);

-- ─── Contracts (Beckn v2 transaction lifecycle) ─────────────
CREATE TABLE contracts (
    id              SERIAL PRIMARY KEY,
    contract_code   TEXT NOT NULL UNIQUE,
    transaction_id  TEXT NOT NULL UNIQUE,
    message_id      TEXT,
    agent_id        INTEGER REFERENCES agents(id),
    provider_id     INTEGER REFERENCES providers(id),
    bap_id          TEXT,
    bpp_id          TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'ACTIVE', 'COMPLETED', 'FAILED', 'CANCELLED')),
    commitments     JSONB NOT NULL DEFAULT '[]',
    consideration   JSONB NOT NULL DEFAULT '[]',
    performance     JSONB NOT NULL DEFAULT '[]',
    settlements     JSONB NOT NULL DEFAULT '[]',
    participants    JSONB NOT NULL DEFAULT '[]',
    execution_id    TEXT,
    total_amount    NUMERIC(12,2),
    currency        CHAR(3) DEFAULT 'INR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    initialized_at  TIMESTAMPTZ,
    confirmed_at    TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_contracts_transaction ON contracts(transaction_id);
CREATE INDEX idx_contracts_status ON contracts(status);
CREATE INDEX idx_contracts_agent ON contracts(agent_id);

-- ─── Callbacks (BAP-side on_* responses) ────────────────────
CREATE TABLE callbacks (
    id              SERIAL PRIMARY KEY,
    transaction_id  TEXT NOT NULL,
    action          VARCHAR(30) NOT NULL,
    context         JSONB NOT NULL DEFAULT '{}',
    message         JSONB NOT NULL DEFAULT '{}',
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_callbacks_transaction ON callbacks(transaction_id);
CREATE INDEX idx_callbacks_action ON callbacks(action);

-- ─── Executions (Orchestrator tracking) ─────────────────────
CREATE TABLE executions (
    id              SERIAL PRIMARY KEY,
    execution_code  TEXT NOT NULL UNIQUE,
    contract_id     INTEGER REFERENCES contracts(id),
    agent_id        INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT')),
    input_payload   JSONB,
    result          JSONB,
    error_message   TEXT,
    latency_ms      INTEGER,
    tokens_input    INTEGER,
    tokens_output   INTEGER,
    model_used      TEXT,
    timeout_ms      INTEGER DEFAULT 30000,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_executions_contract ON executions(contract_id);
CREATE INDEX idx_executions_status ON executions(status);
