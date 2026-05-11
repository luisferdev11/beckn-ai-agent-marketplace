-- 004_provider_mode_and_credentials.sql
-- Adds integration mode to providers and encrypted credentials to agents.
-- integration_mode: 'managed' (we run the agent, publisher gives API key)
--                   'external' (publisher hosts their own endpoint)
-- credentials: JSONB storing encrypted API keys for managed agents.

-- ============================================================
-- PROVIDERS: integration mode
-- ============================================================
ALTER TABLE providers
  ADD COLUMN IF NOT EXISTS integration_mode VARCHAR(20) NOT NULL DEFAULT 'managed';

ALTER TABLE providers
  ADD CONSTRAINT providers_integration_mode_check
  CHECK (integration_mode IN ('managed', 'external'));

-- ============================================================
-- AGENTS: encrypted credentials
-- ============================================================
ALTER TABLE agents
  ADD COLUMN IF NOT EXISTS credentials JSONB NOT NULL DEFAULT '{}';
