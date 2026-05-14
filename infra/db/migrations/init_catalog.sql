-- init_catalog.sql — Catalog domain (beckn_catalog)
-- Tables: categories, providers, agents, users
-- Used by: BPP, Frontend (publisher, admin, auth)

-- ─── Categories ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    display_name    JSONB NOT NULL DEFAULT '{}',
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Providers ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS providers (
    id              SERIAL PRIMARY KEY,
    subscriber_id   TEXT NOT NULL UNIQUE,
    bpp_uri         TEXT NOT NULL,
    public_key      TEXT,
    organization    JSONB NOT NULL DEFAULT '{}',
    integration_mode VARCHAR(20) NOT NULL DEFAULT 'external',
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Agents (AgentFacts-compatible) ─────────────────────────
-- All agent logic is external: publishers register an endpoint URL
-- and the marketplace calls it directly. No API keys, prompts, or
-- LLM config stored here.
CREATE TABLE IF NOT EXISTS agents (
    id                  SERIAL PRIMARY KEY,
    provider_id         INTEGER NOT NULL REFERENCES providers(id),
    category_id         INTEGER NOT NULL REFERENCES categories(id),
    beckn_id            TEXT UNIQUE,
    agentfacts_id       TEXT,
    agent_urn           TEXT,
    label               TEXT,
    agent_name          JSONB NOT NULL DEFAULT '{}',
    description         TEXT,
    version             VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    access_point_url    TEXT NOT NULL,
    interaction_type    VARCHAR(20) NOT NULL DEFAULT 'sync'
                        CHECK (interaction_type IN ('sync', 'async', 'streaming')),
    capabilities        JSONB NOT NULL DEFAULT '{}',
    skills              JSONB NOT NULL DEFAULT '[]',
    input_schema        JSONB NOT NULL DEFAULT '{}',
    output_schema       JSONB NOT NULL DEFAULT '{}',
    pricing_model       JSONB NOT NULL DEFAULT '{}',
    sla                 JSONB NOT NULL DEFAULT '{}',
    jurisdiction        VARCHAR(10),
    endpoints           JSONB NOT NULL DEFAULT '{"static": []}',
    status              VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive', 'deprecated')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_provider ON agents(provider_id);
CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_capabilities ON agents USING GIN (capabilities);
CREATE INDEX IF NOT EXISTS idx_agents_skills ON agents USING GIN (skills);

-- ─── Users (authentication) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    role                VARCHAR(20) NOT NULL DEFAULT 'consumer'
                        CHECK (role IN ('consumer', 'publisher', 'admin')),
    subscription_status VARCHAR(20) DEFAULT 'free'
                        CHECK (subscription_status IN ('free', 'active', 'cancelled')),
    provider_id         INTEGER REFERENCES providers(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_provider ON users(provider_id);

-- ─── Seed: category and provider ────────────────────────────
INSERT INTO categories (name, display_name, description)
VALUES ('ai-agent', '{"en": "AI Agent"}', 'Artificial intelligence agents')
ON CONFLICT (name) DO NOTHING;

INSERT INTO providers (subscriber_id, bpp_uri, organization)
VALUES (
    'bpp.example.com',
    'http://bpp-provider:3002',
    '{"name": "AI Solutions Demo Provider", "shortDesc": "Demo provider of AI agents for the Beckn marketplace"}'
)
ON CONFLICT (subscriber_id) DO NOTHING;

-- ─── Seed: 3 demo agents ────────────────────────────────────
DO $$
DECLARE
    v_provider_id INTEGER;
    v_category_id INTEGER;
BEGIN
    SELECT id INTO v_provider_id FROM providers WHERE subscriber_id = 'bpp.example.com';
    SELECT id INTO v_category_id FROM categories WHERE name = 'ai-agent';

    INSERT INTO agents (
        provider_id, category_id,
        beckn_id, agentfacts_id, agent_urn, label,
        agent_name, description, version,
        access_point_url, interaction_type,
        capabilities, skills,
        input_schema, output_schema,
        pricing_model, sla, jurisdiction, endpoints
    ) VALUES
    (
        v_provider_id, v_category_id,
        'agent-summarizer-001',
        'beckn-marketplace:summarizer-v1',
        'urn:agent:beckn-marketplace:LegalDocumentSummarizer',
        'Legal Document Summarizer',
        '{"en": "Legal Document Summarizer"}',
        'Summarizes legal and regulatory documents in Hindi and English',
        '1.0.0',
        'http://agents:3004',
        'sync',
        '{"modalities": ["text"], "streaming": false, "batch": false, "authentication": {"methods": ["jwt"]}}',
        '[{"id": "document_summary", "description": "Summarizes legal and regulatory documents", "inputModes": ["text/plain", "application/pdf"], "outputModes": ["application/json"], "supportedLanguages": ["en", "hi"], "latencyBudgetMs": 5000, "maxTokens": 4096}, {"id": "legal_analysis", "description": "Analyzes legal clauses and provisions", "inputModes": ["text/plain"], "outputModes": ["application/json"], "supportedLanguages": ["en", "hi"], "latencyBudgetMs": 5000}]',
        '{}', '{}',
        '{"model": "per_task", "currency": "INR", "value": 6.00}',
        '{"maxLatencyMs": 120000, "accuracy": 0.95, "uptime": 0.995}',
        'IN',
        '{"static": ["http://onix-bpp:8082/bpp/caller"]}'
    ),
    (
        v_provider_id, v_category_id,
        'agent-code-reviewer-001',
        'beckn-marketplace:code-reviewer-v1',
        'urn:agent:beckn-marketplace:CodeReviewAssistant',
        'Code Review Assistant',
        '{"en": "Code Review Assistant"}',
        'Reviews code for bugs, security issues, and best practices',
        '1.0.0',
        'http://agents:3004',
        'sync',
        '{"modalities": ["text"], "streaming": false, "batch": false, "authentication": {"methods": ["jwt"]}}',
        '[{"id": "code_review", "description": "Reviews code for bugs and quality issues", "inputModes": ["text/plain", "application/zip"], "outputModes": ["application/json"], "supportedLanguages": ["en"], "latencyBudgetMs": 30000, "maxTokens": 8192}, {"id": "security_analysis", "description": "Detects OWASP Top 10 vulnerabilities", "inputModes": ["text/plain"], "outputModes": ["application/json"], "supportedLanguages": ["en"], "latencyBudgetMs": 30000}, {"id": "best_practices", "description": "Checks adherence to coding standards", "inputModes": ["text/plain"], "outputModes": ["application/json"], "supportedLanguages": ["en"], "latencyBudgetMs": 30000}]',
        '{}', '{}',
        '{"model": "per_task", "currency": "INR", "value": 10.00}',
        '{"maxLatencyMs": 120000, "accuracy": 0.90, "uptime": 0.99}',
        'IN',
        '{"static": ["http://onix-bpp:8082/bpp/caller"]}'
    ),
    (
        v_provider_id, v_category_id,
        'agent-data-extractor-001',
        'beckn-marketplace:data-extractor-v1',
        'urn:agent:beckn-marketplace:InvoiceDataExtractor',
        'Invoice Data Extractor',
        '{"en": "Invoice Data Extractor"}',
        'Extracts structured data from invoices and financial documents',
        '1.0.0',
        'http://agents:3004',
        'sync',
        '{"modalities": ["text", "image"], "streaming": false, "batch": true, "authentication": {"methods": ["jwt"]}}',
        '[{"id": "data_extraction", "description": "Extracts structured fields from financial documents", "inputModes": ["image/jpeg", "image/png", "application/pdf"], "outputModes": ["application/json"], "supportedLanguages": ["en", "hi", "ta"], "latencyBudgetMs": 10000, "maxTokens": 4096}, {"id": "ocr", "description": "Optical character recognition for scanned documents", "inputModes": ["image/jpeg", "image/png"], "outputModes": ["text/plain"], "supportedLanguages": ["en", "hi", "ta"], "latencyBudgetMs": 5000}, {"id": "invoice_processing", "description": "Parses invoice line items, totals, and vendor details", "inputModes": ["application/pdf", "image/jpeg", "image/png"], "outputModes": ["application/json"], "supportedLanguages": ["en", "hi"], "latencyBudgetMs": 10000}]',
        '{}', '{}',
        '{"model": "per_task", "currency": "INR", "value": 4.00}',
        '{"maxLatencyMs": 120000, "accuracy": 0.92, "uptime": 0.995}',
        'IN',
        '{"static": ["http://onix-bpp:8082/bpp/caller"]}'
    )
    ON CONFLICT (beckn_id) DO NOTHING;
END $$;

-- ─── Seed: test users ────────────────────────────────────────
-- bcrypt hash for "Marketplace2026!" with 12 salt rounds
INSERT INTO users (email, password_hash, role, subscription_status)
VALUES
  ('baructest@gmail.com',
   '$2b$12$VhZpZb4sN//9UvRlETYWTu2h7FRoo.XbSBbGwdviTTUN4lC5oApkK',
   'admin', 'active'),
  ('generico@gmail.com',
   '$2b$12$VhZpZb4sN//9UvRlETYWTu2h7FRoo.XbSBbGwdviTTUN4lC5oApkK',
   'consumer', 'free')
ON CONFLICT (email) DO NOTHING;
