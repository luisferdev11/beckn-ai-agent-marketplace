-- 003_users_and_stats.sql
-- Adds user authentication and agent statistics tables.
-- users.id is UUID; provider_id is INTEGER to match providers.id (SERIAL).
-- agent_stats.agent_id is INTEGER to match agents.id (SERIAL).

-- ============================================================
-- USERS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               VARCHAR(255) UNIQUE NOT NULL,
  password_hash       VARCHAR(255) NOT NULL,
  role                VARCHAR(20)  NOT NULL DEFAULT 'consumer'
                      CHECK (role IN ('consumer', 'publisher', 'admin')),
  subscription_status VARCHAR(20)  DEFAULT 'free'
                      CHECK (subscription_status IN ('free', 'active', 'cancelled')),
  provider_id         INTEGER REFERENCES providers(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ  DEFAULT NOW(),
  updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_provider ON users(provider_id);

-- ============================================================
-- AGENT STATS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_stats (
  id             SERIAL PRIMARY KEY,
  agent_id       INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  total_queries  INTEGER DEFAULT 0,
  unique_users   INTEGER DEFAULT 0,
  last_used_at   TIMESTAMPTZ,
  week_queries   INTEGER DEFAULT 0,
  recorded_at    DATE DEFAULT CURRENT_DATE
);

CREATE INDEX idx_agent_stats_agent ON agent_stats(agent_id);
CREATE INDEX idx_agent_stats_recorded ON agent_stats(recorded_at);

-- ============================================================
-- SEED USERS
-- bcrypt hash for "Marketplace2026!" with 12 salt rounds:
-- Generated with: bcryptjs.hash('Marketplace2026!', 12)
-- ============================================================
INSERT INTO users (email, password_hash, role, subscription_status)
VALUES
  ('baructest@gmail.com',
   '$2b$12$VhZpZb4sN//9UvRlETYWTu2h7FRoo.XbSBbGwdviTTUN4lC5oApkK',
   'admin', 'active'),
  ('generico@gmail.com',
   '$2b$12$VhZpZb4sN//9UvRlETYWTu2h7FRoo.XbSBbGwdviTTUN4lC5oApkK',
   'consumer', 'free')
ON CONFLICT (email) DO NOTHING;

-- ============================================================
-- SEED AGENT STATS (mock data for the 5 existing agents)
-- ============================================================
INSERT INTO agent_stats (agent_id, total_queries, unique_users, last_used_at, week_queries)
VALUES
  (1,  142, 38, NOW() - INTERVAL '2 hours',  27),
  (5,  289, 95, NOW() - INTERVAL '30 minutes', 64),
  (6,   87, 22, NOW() - INTERVAL '1 day',     12),
  (7,  203, 61, NOW() - INTERVAL '4 hours',   45),
  (8,   56, 15, NOW() - INTERVAL '3 days',     8)
ON CONFLICT DO NOTHING;
