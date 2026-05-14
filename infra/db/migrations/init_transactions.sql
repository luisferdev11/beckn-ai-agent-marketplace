-- init_transactions.sql — Transaction domain (beckn_transactions)
-- Tables: contracts, callbacks, executions
-- Used by: BAP, BPP

-- ─── Contracts (Beckn v2 transaction lifecycle) ─────────────
CREATE TABLE IF NOT EXISTS contracts (
    id              SERIAL PRIMARY KEY,
    contract_code   TEXT NOT NULL UNIQUE,
    transaction_id  TEXT NOT NULL UNIQUE,
    message_id      TEXT,
    agent_id        INTEGER,
    provider_id     INTEGER,
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

CREATE INDEX IF NOT EXISTS idx_contracts_transaction ON contracts(transaction_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_agent ON contracts(agent_id);

-- ─── Callbacks (BAP-side on_* responses) ────────────────────
CREATE TABLE IF NOT EXISTS callbacks (
    id              SERIAL PRIMARY KEY,
    transaction_id  TEXT NOT NULL,
    action          VARCHAR(30) NOT NULL,
    context         JSONB NOT NULL DEFAULT '{}',
    message         JSONB NOT NULL DEFAULT '{}',
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_callbacks_transaction ON callbacks(transaction_id);
CREATE INDEX IF NOT EXISTS idx_callbacks_action ON callbacks(action);

-- ─── Executions (Orchestrator tracking) ─────────────────────
CREATE TABLE IF NOT EXISTS executions (
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
    timeout_ms      INTEGER DEFAULT 120000,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_executions_contract ON executions(contract_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
