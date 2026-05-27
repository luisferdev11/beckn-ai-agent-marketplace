-- 003_ratings.sql — BPP-side ratings log + local agent aggregates
--
-- The BPP is the system of record for ratings it receives — it owns the
-- relationship with its catalog of agents and is the source the
-- marketplace CDS pulls from. This migration adds:
--
--   ratings_received   raw rating events delivered via /rate webhook
--   v_agent_ratings    rolling aggregate per agent — used internally by
--                      the provider portal; the canonical aggregate for
--                      discover ranking lives at the CDS
--                      (see mock-network migration 003_ratings_agg.sql).

CREATE TABLE ratings_received (
    id              SERIAL PRIMARY KEY,
    transaction_id  TEXT NOT NULL,
    contract_code   TEXT,
    target_id       TEXT NOT NULL,                          -- agent beckn_id (no FK; targets vary)
    target_type     VARCHAR(20) NOT NULL DEFAULT 'agent'
                    CHECK (target_type IN ('agent', 'provider', 'contract', 'fulfillment')),
    score           NUMERIC(3,2) NOT NULL CHECK (score >= 1.0 AND score <= 5.0),
    score_min       NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    score_max       NUMERIC(3,2) NOT NULL DEFAULT 5.0,
    feedback        TEXT,
    bap_id          TEXT,                                   -- counterparty
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One rating per (transaction, target) — replace-or-insert semantics enforced
-- in the handler.
CREATE UNIQUE INDEX uq_ratings_received_txn_target
    ON ratings_received(transaction_id, target_id, target_type);

CREATE INDEX idx_ratings_received_target ON ratings_received(target_id);
CREATE INDEX idx_ratings_received_bap    ON ratings_received(bap_id);

-- Materialized view-style aggregate (regular VIEW for now — population is
-- small enough that recomputing per query is fine; promote to a materialized
-- view once cardinality grows).
CREATE OR REPLACE VIEW v_agent_ratings AS
SELECT
    target_id AS agent_beckn_id,
    COUNT(*) AS rating_count,
    AVG(score)::NUMERIC(4,3) AS avg_score,
    MAX(received_at) AS last_rated_at
FROM ratings_received
WHERE target_type = 'agent'
GROUP BY target_id;
