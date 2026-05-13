-- 005_agent_llm_config.sql
-- Adds LLM configuration columns to agents so publishers can register
-- any LLM-backed agent from the portal without backend code changes.
-- The agents service uses litellm with these values to call any provider.

-- ============================================================
-- AGENTS: LLM configuration
-- ============================================================
ALTER TABLE agents ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(40);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS llm_model VARCHAR(100);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS system_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS temperature NUMERIC(3,2) DEFAULT 0.7;

-- ============================================================
-- Backfill existing seed agents (all were using Groq)
-- ============================================================
UPDATE agents
SET llm_provider = 'groq',
    llm_model    = 'llama-3.3-70b-versatile',
    system_prompt = 'You are an expert code reviewer. Analyze the provided code and give structured feedback covering: 1) Code quality & readability, 2) Potential bugs or logic errors, 3) Security issues, 4) Performance improvements, 5) Best practices & suggestions.',
    temperature  = 0.3
WHERE beckn_id IN ('agent-code-reviewer-001', 'agent-summarizer-001', 'agent-data-extractor-001');

UPDATE agents
SET llm_provider = 'groq',
    llm_model    = 'llama-3.3-70b-versatile',
    system_prompt = 'You are a helpful, knowledgeable AI assistant. Answer the user''s question clearly and thoroughly. Respond in the same language the user writes in.',
    temperature  = 0.7
WHERE beckn_id = 'text-generator';
