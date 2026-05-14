-- init_metrics.sql — Metrics domain (beckn_metrics)
-- Tables: agent_stats
-- Used by: Orchestrator, Frontend (publisher stats)
--
-- Note: agent_id references agents in the catalog DB by convention
-- (no cross-database FK). Application code ensures consistency.

CREATE TABLE IF NOT EXISTS agent_stats (
    id             SERIAL PRIMARY KEY,
    agent_id       INTEGER NOT NULL,
    total_queries  INTEGER DEFAULT 0,
    unique_users   INTEGER DEFAULT 0,
    last_used_at   TIMESTAMPTZ,
    week_queries   INTEGER DEFAULT 0,
    recorded_at    DATE DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_agent_stats_agent ON agent_stats(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_stats_recorded ON agent_stats(recorded_at);
