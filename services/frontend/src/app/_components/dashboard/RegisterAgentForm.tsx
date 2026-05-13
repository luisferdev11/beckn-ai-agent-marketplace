'use client';

import { useState, useEffect } from 'react';

interface Props {
  token: string;
  integrationMode: 'managed' | 'external';
  onSuccess: () => void;
  onCancel: () => void;
}

interface Category {
  id: number;
  name: string;
  display_name: { en?: string };
}

const LLM_PROVIDERS = [
  { value: 'groq', label: 'Groq', hint: 'llama-3.3-70b-versatile, mixtral-8x7b-32768' },
  { value: 'openai', label: 'OpenAI', hint: 'gpt-4o, gpt-4o-mini' },
  { value: 'anthropic', label: 'Anthropic', hint: 'claude-sonnet-4-20250514, claude-haiku-4-5-20251001' },
  { value: 'gemini', label: 'Google Gemini', hint: 'gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash' },
  { value: 'mistral', label: 'Mistral', hint: 'mistral-large-latest, mistral-small-latest' },
  { value: 'together_ai', label: 'Together AI', hint: 'meta-llama/Llama-3-70b' },
  { value: 'deepseek', label: 'DeepSeek', hint: 'deepseek-chat, deepseek-reasoner' },
];

export function RegisterAgentForm({ token, integrationMode, onSuccess, onCancel }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState<number | ''>('');
  const [pricingType, setPricingType] = useState('per_task');
  const [pricingValue, setPricingValue] = useState('');
  const [endpoint, setEndpoint] = useState(integrationMode === 'managed' ? 'http://agents:3004' : '');
  const [apiKey, setApiKey] = useState('');
  const [llmProvider, setLlmProvider] = useState('groq');
  const [llmModel, setLlmModel] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [temperature, setTemperature] = useState('0.7');
  const [status, setStatus] = useState('active');
  const [categories, setCategories] = useState<Category[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('/api/categories')
      .then(r => r.json())
      .then(setCategories)
      .catch(() => {});
  }, []);

  const selectedProvider = LLM_PROVIDERS.find(p => p.value === llmProvider);

  async function handleSubmit() {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = 'Name required';
    if (!categoryId) e.category = 'Category required';
    if (description.length > 160) e.description = 'Max 160 characters';
    if (integrationMode === 'managed') {
      if (!apiKey.trim()) e.apiKey = 'API key required for managed agents';
      if (!llmModel.trim()) e.llmModel = 'Model name required';
      if (!systemPrompt.trim()) e.systemPrompt = 'System prompt required';
    }
    if (integrationMode === 'external' && !endpoint.trim()) e.endpoint = 'Endpoint URL required for external agents';
    setErrors(e);
    if (Object.keys(e).length) return;

    setLoading(true);
    const body: Record<string, unknown> = {
      agent_name: name,
      description,
      category_id: categoryId,
      pricing_model: { model: pricingType, value: parseFloat(pricingValue) || 0, currency: 'INR' },
      access_point_url: integrationMode === 'managed' ? 'http://agents:3004' : endpoint,
      status,
    };

    if (integrationMode === 'managed') {
      body.api_key = apiKey;
      body.llm_provider = llmProvider;
      body.llm_model = llmModel;
      body.system_prompt = systemPrompt;
      body.temperature = parseFloat(temperature) || 0.7;
    }

    const res = await fetch('/api/publisher/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });

    setLoading(false);
    if (res.ok) {
      onSuccess();
    } else {
      try {
        const data = await res.json();
        setErrors({ submit: data.error || 'Failed to create agent' });
      } catch {
        setErrors({ submit: `Server error (${res.status})` });
      }
    }
  }

  const inputStyle = (field: string) => ({
    width: '100%', padding: '10px 14px', borderRadius: 6,
    border: `1px solid ${errors[field] ? 'var(--trust-low)' : 'var(--border-default)'}`,
    background: 'var(--bg-surface)', fontFamily: 'var(--font-plex)',
    fontSize: 14, color: 'var(--text-primary)', outline: 'none',
  });

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }} onClick={onCancel}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--bg-surface)', borderRadius: 10,
        border: '1px solid var(--border-subtle)', padding: '28px',
        width: '100%', maxWidth: 520, maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 8px 40px rgba(0,0,0,0.2)',
      }}>
        <h3 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 4 }}>
          Register New Agent
        </h3>
        <div style={{
          fontSize: 11, fontFamily: 'var(--font-mono)', marginBottom: 16,
          padding: '3px 8px', borderRadius: 4, display: 'inline-block',
          background: integrationMode === 'managed' ? 'var(--accent-dim)' : 'rgba(0,135,90,0.08)',
          color: integrationMode === 'managed' ? 'var(--infosys-cobalt)' : 'var(--trust-high)',
        }}>
          {integrationMode === 'managed' ? 'MANAGED — We run your agent' : 'EXTERNAL — Your endpoint'}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Agent Name</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="My AI Agent" style={inputStyle('name')} />
            {errors.name && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.name}</span>}
          </div>

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
              Short Description ({description.length}/160)
            </label>
            <input value={description} onChange={e => setDescription(e.target.value.slice(0, 160))} placeholder="Brief description of what this agent does" style={inputStyle('description')} />
            {errors.description && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.description}</span>}
          </div>

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Category</label>
            <select value={categoryId} onChange={e => setCategoryId(Number(e.target.value))} style={{ ...inputStyle('category'), cursor: 'pointer' }}>
              <option value="">Select category...</option>
              {categories.map(c => (
                <option key={c.id} value={c.id}>{c.display_name?.en || c.name}</option>
              ))}
            </select>
            {errors.category && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.category}</span>}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Pricing Model</label>
              <select value={pricingType} onChange={e => setPricingType(e.target.value)} style={{ ...inputStyle(''), cursor: 'pointer' }}>
                <option value="per_task">Per Task</option>
                <option value="subscription">Monthly Subscription</option>
                <option value="free">Free</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Price (INR)</label>
              <input type="number" value={pricingValue} onChange={e => setPricingValue(e.target.value)} placeholder="0.00" style={inputStyle('')} />
            </div>
          </div>

          {/* Managed mode: LLM configuration */}
          {integrationMode === 'managed' && (
            <>
              <div style={{
                borderTop: '1px solid var(--border-subtle)', paddingTop: 12, marginTop: 4,
              }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 8 }}>
                  LLM Configuration
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
                    Provider <span style={{ color: 'var(--trust-low)' }}>*</span>
                  </label>
                  <select value={llmProvider} onChange={e => setLlmProvider(e.target.value)} style={{ ...inputStyle(''), cursor: 'pointer' }}>
                    {LLM_PROVIDERS.map(p => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
                    Model <span style={{ color: 'var(--trust-low)' }}>*</span>
                  </label>
                  <input value={llmModel} onChange={e => setLlmModel(e.target.value)}
                    placeholder={selectedProvider?.hint?.split(',')[0]?.trim() || 'model-name'}
                    style={inputStyle('llmModel')} />
                  {errors.llmModel && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.llmModel}</span>}
                </div>
              </div>
              {selectedProvider?.hint && (
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: -4 }}>
                  Available: {selectedProvider.hint}
                </div>
              )}

              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
                  API Key <span style={{ color: 'var(--trust-low)' }}>*</span>
                </label>
                <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                  placeholder="sk-... or gsk_... or AIza..."
                  style={inputStyle('apiKey')} />
                {errors.apiKey && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.apiKey}</span>}
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
                  Your key is encrypted before storage and never shown again.
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
                  System Prompt <span style={{ color: 'var(--trust-low)' }}>*</span>
                </label>
                <textarea
                  value={systemPrompt}
                  onChange={e => setSystemPrompt(e.target.value)}
                  placeholder="You are an expert at... Respond with..."
                  rows={4}
                  style={{
                    ...inputStyle('systemPrompt'),
                    resize: 'vertical', minHeight: 80,
                  }}
                />
                {errors.systemPrompt && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.systemPrompt}</span>}
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
                  Instructions that define your agent&apos;s behavior and personality.
                </div>
              </div>

              <div style={{ maxWidth: 120 }}>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Temperature</label>
                <input type="number" step="0.1" min="0" max="2" value={temperature}
                  onChange={e => setTemperature(e.target.value)}
                  style={inputStyle('')} />
              </div>
            </>
          )}

          {/* External: Endpoint URL field */}
          {integrationMode === 'external' && (
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
                Agent Endpoint URL <span style={{ color: 'var(--trust-low)' }}>*</span>
              </label>
              <input value={endpoint} onChange={e => setEndpoint(e.target.value)} placeholder="https://api.your-company.com/agent" style={inputStyle('endpoint')} />
              {errors.endpoint && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.endpoint}</span>}
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
                Must accept POST /task with JSON body and return status/result/usage.
              </div>
            </div>
          )}

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Initial Status</label>
            <select value={status} onChange={e => setStatus(e.target.value)} style={{ ...inputStyle(''), cursor: 'pointer' }}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>

        {errors.submit && (
          <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 6, background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)', color: 'var(--trust-low)', fontSize: 12 }}>
            {errors.submit}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
          <button onClick={onCancel} style={{
            flex: 1, padding: '10px', borderRadius: 6, border: '1px solid var(--border-default)',
            background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
            fontSize: 13, cursor: 'pointer',
          }}>
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={loading} style={{
            flex: 2, padding: '10px', borderRadius: 6, border: 'none',
            background: loading ? 'var(--bg-elevated)' : 'var(--infosys-cobalt)',
            color: loading ? 'var(--text-tertiary)' : '#fff', fontFamily: 'var(--font-plex)',
            fontSize: 13, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
          }}>
            {loading ? 'Creating...' : 'Create Agent'}
          </button>
        </div>
      </div>
    </div>
  );
}
