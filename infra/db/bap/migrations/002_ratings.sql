-- 002_ratings.sql — BAP-side ratings log
--
-- The BAP records each rating IT submits to a BPP. This is the buyer's
-- audit trail of feedback given. The actual canonical rating lives on
-- the BPP side (and the marketplace aggregator at the CDS); this table
-- exists so the BAP can show the user the history of what they rated
-- and prevent accidental double-ratings on the same transaction.

CREATE TABLE ratings_sent (
    id              SERIAL PRIMARY KEY,
    transaction_id  TEXT NOT NULL,                          -- correlates to contracts.transaction_id
    target_id       TEXT NOT NULL,                          -- usually the agent_beckn_id
    target_type     VARCHAR(20) NOT NULL DEFAULT 'agent'    -- agent | provider | contract
                    CHECK (target_type IN ('agent', 'provider', 'contract', 'fulfillment')),
    score           NUMERIC(3,2) NOT NULL CHECK (score >= 1.0 AND score <= 5.0),
    score_min       NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    score_max       NUMERIC(3,2) NOT NULL DEFAULT 5.0,
    feedback        TEXT,                                   -- optional free-form review
    bpp_id          TEXT,                                   -- counterparty (no FK — lives in BPP)
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One rating per (transaction, target) — re-rating overwrites via app logic,
-- never duplicates.
CREATE UNIQUE INDEX uq_ratings_sent_txn_target
    ON ratings_sent(transaction_id, target_id, target_type);

CREATE INDEX idx_ratings_sent_target  ON ratings_sent(target_id);
CREATE INDEX idx_ratings_sent_bpp     ON ratings_sent(bpp_id);
