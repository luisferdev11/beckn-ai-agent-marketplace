'use client';

import { useState, useEffect } from 'react';

interface Props {
  token: string;
  onSuccess: () => void;
  onCancel: () => void;
}

interface Category {
  id: number;
  name: string;
  display_name: { en?: string };
}

export function RegisterAgentForm({ token, onSuccess, onCancel }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState<number | ''>('');
  const [pricingType, setPricingType] = useState('per_task');
  const [pricingValue, setPricingValue] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [status, setStatus] = useState('active');
  const [inputSchema, setInputSchema] = useState('');
  const [outputSchema, setOutputSchema] = useState('');
  const [categories, setCategories] = useState<Category[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // Parse a textarea value as a JSON Schema object. Returns the parsed
  // object, or an error message describing why it is not acceptable. A
  // valid contract must be a non-empty JSON object (the marketplace
  // rejects empty / non-object schemas at publish time — strict mode).
  function parseSchema(raw: string): { value?: Record<string, unknown>; error?: string } {
    const trimmed = raw.trim();
    if (!trimmed) return { error: 'Required — declare a JSON Schema' };
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch (err) {
      return { error: `Invalid JSON: ${(err as Error).message}` };
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { error: 'Must be a JSON object (e.g. {"type":"object",...})' };
    }
    if (Object.keys(parsed as object).length === 0) {
      return { error: 'Empty schema constrains nothing — add at least "type"' };
    }
    return { value: parsed as Record<string, unknown> };
  }

  useEffect(() => {
    fetch('/api/categories')
      .then(r => r.json())
      .then(setCategories)
      .catch(() => {});
  }, []);

  async function handleSubmit() {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = 'Name required';
    if (!categoryId) e.category = 'Category required';
    if (description.length > 160) e.description = 'Max 160 characters';
    if (!endpoint.trim()) e.endpoint = 'Endpoint URL required';

    const inParsed = parseSchema(inputSchema);
    if (inParsed.error) e.inputSchema = inParsed.error;
    const outParsed = parseSchema(outputSchema);
    if (outParsed.error) e.outputSchema = outParsed.error;

    setErrors(e);
    if (Object.keys(e).length) return;

    setLoading(true);
    const body: Record<string, unknown> = {
      agent_name: name,
      description,
      category_id: categoryId,
      pricing_model: { model: pricingType, value: parseFloat(pricingValue) || 0, currency: 'INR' },
      access_point_url: endpoint,
      status,
      input_schema: inParsed.value,
      output_schema: outParsed.value,
    };

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
        <h3 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 16 }}>
          Register New Agent
        </h3>

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

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
              Agent Endpoint URL <span style={{ color: 'var(--trust-low)' }}>*</span>
            </label>
            <input value={endpoint} onChange={e => setEndpoint(e.target.value)} placeholder="https://api.your-company.com/agent" style={inputStyle('endpoint')} />
            {errors.endpoint && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.endpoint}</span>}
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
              The URL where your agent receives requests. Must accept POST with JSON body.
            </div>
          </div>

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Initial Status</label>
            <select value={status} onChange={e => setStatus(e.target.value)} style={{ ...inputStyle(''), cursor: 'pointer' }}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>

          {/* Rigorous schema contracts — required so the agent can be probed
              and routed by the orchestrator pipeline (strict mode). */}
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
              Input Schema (JSON Schema) <span style={{ color: 'var(--trust-low)' }}>*</span>
            </label>
            <textarea
              value={inputSchema}
              onChange={e => setInputSchema(e.target.value)}
              placeholder={'{\n  "type": "object",\n  "properties": { "text": { "type": "string" } },\n  "required": ["text"]\n}'}
              rows={6}
              style={{ ...inputStyle('inputSchema'), fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical' }}
            />
            {errors.inputSchema && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.inputSchema}</span>}
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
              Describes the structured input your agent expects. Validated as JSON before submit.
            </div>
          </div>

          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>
              Output Schema (JSON Schema) <span style={{ color: 'var(--trust-low)' }}>*</span>
            </label>
            <textarea
              value={outputSchema}
              onChange={e => setOutputSchema(e.target.value)}
              placeholder={'{\n  "type": "object",\n  "properties": { "result": { "type": "string" } },\n  "required": ["result"]\n}'}
              rows={6}
              style={{ ...inputStyle('outputSchema'), fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical' }}
            />
            {errors.outputSchema && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.outputSchema}</span>}
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
              Describes the structured output your agent guarantees. Validated as JSON before submit.
            </div>
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
