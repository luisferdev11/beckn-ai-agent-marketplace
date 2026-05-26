-- 002_seed_data.sql
-- Seed data for the BPP: demo category, demo provider, and 3 demo agents.
-- Schema (including beckn_id, agentfacts_id, agent_urn, label, and the
-- AgentFacts-shaped capabilities default) lives in 001_schema.sql.

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
        input_schema, output_schema, model_provider,
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
        '{"type": "object", "properties": {"document": {"type": "string"}, "language": {"type": "string"}}, "required": ["document"]}',
        '{"type": "object", "properties": {"summary": {"type": "string"}, "key_points": {"type": "array", "items": {"type": "string"}}}, "required": ["summary"]}',
        'meta/llama-3.3-70b',
        '{"model": "per_task", "currency": "INR", "value": 6.00}',
        '{"maxLatencyMs": 5000, "accuracy": 0.95, "uptime": 0.995}',
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
        '{"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}, "context": {"type": "string"}}, "required": ["code", "language"]}',
        '{"type": "object", "properties": {"review": {"type": "string"}, "language": {"type": "string"}}, "required": ["review"]}',
        'meta/llama-3.3-70b',
        '{"model": "per_task", "currency": "INR", "value": 10.00}',
        '{"maxLatencyMs": 30000, "accuracy": 0.90, "uptime": 0.99}',
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
        '{"type": "object", "properties": {"document": {"type": "string"}, "format": {"type": "string"}}, "required": ["document"]}',
        '{"type": "object", "properties": {"fields": {"type": "object"}, "raw_text": {"type": "string"}}, "required": ["fields"]}',
        'meta/llama-3.3-70b',
        '{"model": "per_task", "currency": "INR", "value": 4.00}',
        '{"maxLatencyMs": 10000, "accuracy": 0.92, "uptime": 0.995}',
        'IN',
        '{"static": ["http://onix-bpp:8082/bpp/caller"]}'
    )
    ON CONFLICT (beckn_id) DO NOTHING;
END $$;
