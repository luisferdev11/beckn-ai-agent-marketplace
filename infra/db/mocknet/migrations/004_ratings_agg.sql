-- 004_ratings_agg.sql — Marketplace-side rating aggregates per agent.
--
-- Source of truth for the "quality" component in the composite discover
-- score (see app/discover/scoring.py). Populated by BPPs via
-- POST /cds/ratings/ingest when they receive an on_rate; the BPP can
-- batch-resend or backfill at any time without ordering concerns
-- because we store the rolling sum/count and recompute the average on
-- the fly.
--
-- Key choice: (bpp_subscriber_id, agent_beckn_id). agent_beckn_id is the
-- public Beckn ID — same shape we surface in on_discover. Joining onto
-- agent_versions is intentionally a LEFT JOIN: a rating that arrives
-- before the agent's first publish (rare but possible during onboarding)
-- still gets counted; it just doesn't influence discover until the
-- agent gets indexed.

CREATE TABLE agent_ratings_agg (
    bpp_subscriber_id   TEXT NOT NULL,                                  -- soft-FK to subscribers
    agent_beckn_id      TEXT NOT NULL,                                  -- soft-FK to agent_versions.beckn_id
    rating_count        INTEGER NOT NULL DEFAULT 0,
    rating_sum          NUMERIC(14,4) NOT NULL DEFAULT 0,               -- sum of raw scores (1..5 scale)
    avg_score           NUMERIC(4,3) NOT NULL DEFAULT 0,                -- rating_sum / NULLIF(rating_count, 0)
    last_rated_at       TIMESTAMPTZ,
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (bpp_subscriber_id, agent_beckn_id)
);

CREATE INDEX idx_agent_ratings_agg_agent
    ON agent_ratings_agg(agent_beckn_id);
