'use client';

import { useState, useEffect } from 'react';

interface Provider {
  id: number;
  subscriber_id: string;
  organization: { name?: string; shortDesc?: string; contact_email?: string };
  status: string;
}

interface Props {
  onSelect: (providerId: number) => void;
  onCreateNew: () => void;
  selectedId: number | null;
}

export function CompanySearchForm({ onSelect, onCreateNew, selectedId }: Props) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/providers')
      .then(r => r.json())
      .then(setProviders)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = providers.filter(p =>
    (p.organization?.name || '').toLowerCase().includes(search.toLowerCase()) ||
    p.subscriber_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 6, display: 'block' }}>
        Search for your company
      </label>
      <input
        type="text"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search by company name..."
        style={{
          width: '100%', padding: '10px 14px', borderRadius: 6,
          border: '1px solid var(--border-default)', background: 'var(--bg-surface)',
          fontFamily: 'var(--font-plex)', fontSize: 14, color: 'var(--text-primary)',
          outline: 'none', marginBottom: 12,
        }}
      />

      {loading ? (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading companies...</div>
      ) : (
        <div style={{
          maxHeight: 200, overflowY: 'auto', border: '1px solid var(--border-subtle)',
          borderRadius: 6, background: 'var(--bg-surface)',
        }}>
          {filtered.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
              No companies found
            </div>
          ) : (
            filtered.map(p => (
              <div
                key={p.id}
                onClick={() => onSelect(p.id)}
                style={{
                  padding: '10px 14px', cursor: 'pointer',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: selectedId === p.id ? 'var(--accent-dim)' : 'transparent',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { if (selectedId !== p.id) e.currentTarget.style.background = 'var(--bg-elevated)'; }}
                onMouseLeave={e => { if (selectedId !== p.id) e.currentTarget.style.background = 'transparent'; }}
              >
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
                  {p.organization?.name || p.subscriber_id}
                </div>
                {p.organization?.shortDesc && (
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>{p.organization.shortDesc}</div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      <button
        onClick={onCreateNew}
        style={{
          width: '100%', marginTop: 12, padding: '10px', borderRadius: 6,
          border: '1px dashed var(--border-strong)', background: 'transparent',
          color: 'var(--accent)', fontFamily: 'var(--font-plex)', fontSize: 13,
          fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s',
        }}
      >
        + Create new company
      </button>
    </div>
  );
}
