-- 002_seed_data.sql
-- Demo seed data for the Publisher Portal.
--
-- The publisher mock user (publisher@demo.com) has provider_id = 1 hardcoded
-- in mock-users.ts. The provider row below uses id=1 so the dashboard loads
-- real data without any code changes.

-- ── Category ─────────────────────────────────────────────────────────────────

INSERT INTO categories (id, name, display_name, description)
VALUES (1, 'ai-agent', 'AI Agent', 'Artificial intelligence agents for enterprise automation')
ON CONFLICT (name) DO NOTHING;

SELECT setval('categories_id_seq', (SELECT MAX(id) FROM categories));

-- ── Provider (id=1 matches publisher@demo.com provider_id) ───────────────────

INSERT INTO providers (id, subscriber_id, bpp_uri, organization, status, integration_mode)
VALUES (
    1,
    'bpp.demo-agents.com',
    'http://onix-bpp:8082/bpp/receiver',
    '{
        "name": "Demo Agents Inc.",
        "shortDesc": "Provider of AI agents for enterprise automation",
        "contact_email": "agents@demo-agents.com"
    }',
    'active',
    'onix'
)
ON CONFLICT (subscriber_id) DO NOTHING;

SELECT setval('providers_id_seq', (SELECT MAX(id) FROM providers));

-- ── Agents ───────────────────────────────────────────────────────────────────

INSERT INTO agents (
    id, provider_id, category_id, beckn_id, agent_name, label,
    description, version, status, pricing_model, access_point_url
) VALUES
(
    1, 1, 1,
    'agent-summarizer-001',
    '{"en": "Legal Document Summarizer"}',
    'Legal Document Summarizer',
    'Summarizes legal and regulatory documents in Hindi and English. Optimized for RBI circulars, compliance directives, and contracts.',
    '1.2.0', 'active',
    '{"model": "per_task", "currency": "INR", "value": 6.00}',
    'http://agents:3004'
),
(
    2, 1, 1,
    'agent-code-reviewer-001',
    '{"en": "Code Review Assistant"}',
    'Code Review Assistant',
    'Reviews code for bugs, security vulnerabilities, and best practices across 20+ languages.',
    '2.0.1', 'active',
    '{"model": "per_task", "currency": "INR", "value": 10.00}',
    'http://agents:3004'
),
(
    3, 1, 1,
    'agent-data-extractor-001',
    '{"en": "Invoice Data Extractor"}',
    'Invoice Data Extractor',
    'Extracts structured fields from invoices and financial documents. Returns vendor, amounts, line items, and dates as structured JSON.',
    '1.0.3', 'active',
    '{"model": "per_task", "currency": "INR", "value": 4.00}',
    'http://agents:3004'
),
(
    4, 1, 1,
    'agent-text-generator-001',
    '{"en": "Text Generator"}',
    'Text Generator',
    'General-purpose text generation agent. Responds in the same language as the input.',
    '1.0.0', 'inactive',
    '{"model": "per_task", "currency": "INR", "value": 2.00}',
    'http://agents:3004'
)
ON CONFLICT (beckn_id) DO NOTHING;

SELECT setval('agents_id_seq', (SELECT MAX(id) FROM agents));

-- ── Agent stats ───────────────────────────────────────────────────────────────

INSERT INTO agent_stats (agent_id, total_queries, unique_users, week_queries, last_used_at)
VALUES
    (1, 1247, 89,  143, '2026-06-10 14:22:00+00'),
    (2, 892,  67,  98,  '2026-06-11 09:05:00+00'),
    (3, 2103, 134, 287, '2026-06-11 11:47:00+00'),
    (4, 314,  28,  0,   '2026-05-28 16:30:00+00')
ON CONFLICT (agent_id) DO NOTHING;
