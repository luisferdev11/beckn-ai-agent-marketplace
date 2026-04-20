-- 002_seed.sql — Sample data for development/demo
-- Uses the real schema (ai_providers, ai_agents, categories).

-- ─────────────────────────────────────────────
-- Categories
-- ─────────────────────────────────────────────
INSERT INTO categories (category_id, display_name, description, is_active) VALUES
    ('AI-SUMMARIZATION',  '{"en": "Document Summarizer", "es": "Resumen de Documentos"}',   'AI-powered document summarization', true),
    ('AI-EXTRACTION',     '{"en": "Data Extraction", "es": "Extracción de Datos"}',         'Structured data extraction from text', true),
    ('AI-TRANSLATION',    '{"en": "Translation", "es": "Traducción"}',                      'Multi-language translation', true),
    ('AI-CODE-GENERATION','{"en": "Code Generation", "es": "Generación de Código"}',        'AI code generation and debugging', true)
ON CONFLICT (category_id) DO NOTHING;

-- ─────────────────────────────────────────────
-- Providers
-- ─────────────────────────────────────────────
INSERT INTO ai_providers (subscriber_id, bpp_uri, public_key) VALUES
    ('neuralspark-ai.beckn',  'https://api.neuralspark.ai',  'ed25519_pub_key_neuralspark'),
    ('lingualab.beckn',       'https://api.lingualab.io',    'ed25519_pub_key_lingualab')
ON CONFLICT (subscriber_id) DO NOTHING;

-- ─────────────────────────────────────────────
-- Agents
-- ─────────────────────────────────────────────
INSERT INTO ai_agents (
    provider_id, category_id, access_point_url, interaction_type,
    agent_name, version, capabilities, input_schema, output_schema, pricing_model
) VALUES
    (
        (SELECT provider_id FROM ai_providers WHERE subscriber_id = 'neuralspark-ai.beckn'),
        'AI-SUMMARIZATION',
        'https://api.neuralspark.ai/v1/summarize',
        'sync',
        '{"en": "DocSummarizer Pro"}',
        '1.0.0',
        ARRAY['summarization', 'bullet-points', 'executive-summary'],
        '{"type": "object", "properties": {"text": {"type": "string"}}}',
        '{"type": "object", "properties": {"summary": {"type": "string"}}}',
        '{"type": "per_request", "value": 0.05, "currency": "USD"}'
    ),
    (
        (SELECT provider_id FROM ai_providers WHERE subscriber_id = 'neuralspark-ai.beckn'),
        'AI-EXTRACTION',
        'https://api.neuralspark.ai/v1/extract',
        'sync',
        '{"en": "DataExtract Engine"}',
        '1.0.0',
        ARRAY['extraction', 'json-output', 'entity-recognition'],
        '{"type": "object", "properties": {"text": {"type": "string"}}}',
        '{"type": "object", "properties": {"entities": {"type": "array"}}}',
        '{"type": "per_request", "value": 0.08, "currency": "USD"}'
    ),
    (
        (SELECT provider_id FROM ai_providers WHERE subscriber_id = 'lingualab.beckn'),
        'AI-TRANSLATION',
        'https://api.lingualab.io/v1/translate',
        'sync',
        '{"en": "PolyLang Translator"}',
        '1.0.0',
        ARRAY['translation', 'multi-language', 'context-aware'],
        '{"type": "object", "properties": {"text": {"type": "string"}, "target_lang": {"type": "string"}}}',
        '{"type": "object", "properties": {"translated": {"type": "string"}}}',
        '{"type": "per_request", "value": 0.03, "currency": "USD"}'
    ),
    (
        (SELECT provider_id FROM ai_providers WHERE subscriber_id = 'lingualab.beckn'),
        'AI-CODE-GENERATION',
        'https://api.lingualab.io/v1/codegen',
        'sync',
        '{"en": "CodeAssist AI"}',
        '1.0.0',
        ARRAY['code-generation', 'debugging', 'refactoring'],
        '{"type": "object", "properties": {"prompt": {"type": "string"}, "language": {"type": "string"}}}',
        '{"type": "object", "properties": {"code": {"type": "string"}}}',
        '{"type": "per_request", "value": 0.10, "currency": "USD"}'
    );
