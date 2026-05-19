-- 001_schema.sql — BAP (buyer side) PostgreSQL schema
--
-- The BAP only stores what the buyer needs to see:
--   - contracts:  buyer's view of each Beckn transaction
--   - callbacks:  audit log of every on_* response received
--
-- Catalog tables (categories, providers, agents) and execution tracking
-- live on the BPP side and are reachable only through Beckn HTTP messages.
-- bpp_id and agent_beckn_id are TEXT (no FK) because they reference rows
-- that live in another network participant's database.

-- ─── Contracts (Beckn v2 transaction lifecycle — buyer POV) ──
CREATE TABLE contracts (
    id              SERIAL PRIMARY KEY,
    contract_code   TEXT NOT NULL UNIQUE,
    transaction_id  TEXT NOT NULL UNIQUE,
    message_id      TEXT,
    bap_id          TEXT,                       -- self (own BAP subscriber id)
    bpp_id          TEXT,                       -- counterparty (no FK — lives in BPP)
    agent_beckn_id  TEXT,                       -- selected agent beckn_id (no FK)
    status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'ACTIVE', 'COMPLETED', 'FAILED', 'CANCELLED')),
    commitments     JSONB NOT NULL DEFAULT '[]',
    consideration   JSONB NOT NULL DEFAULT '[]',
    performance     JSONB NOT NULL DEFAULT '[]',
    settlements     JSONB NOT NULL DEFAULT '[]',
    participants    JSONB NOT NULL DEFAULT '[]',
    total_amount    NUMERIC(12,2),
    currency        CHAR(3) DEFAULT 'INR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    initialized_at  TIMESTAMPTZ,
    confirmed_at    TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_contracts_transaction ON contracts(transaction_id);
CREATE INDEX idx_contracts_status ON contracts(status);
CREATE INDEX idx_contracts_bpp ON contracts(bpp_id);

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
