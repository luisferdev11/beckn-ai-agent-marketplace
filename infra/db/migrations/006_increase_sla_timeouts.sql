-- 006_increase_sla_timeouts.sql
-- Increase maxLatencyMs for all agents to allow sufficient time for LLM API calls.
-- Previous values (5s, 10s, 30s) were too short for real Groq/OpenAI responses.

UPDATE agents
SET sla = jsonb_set(
    COALESCE(sla, '{}'::jsonb),
    '{maxLatencyMs}',
    '120000'
)
WHERE sla IS NULL
   OR (sla->>'maxLatencyMs')::int < 120000;
