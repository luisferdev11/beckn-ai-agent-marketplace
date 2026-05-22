'use client';

interface Provider {
  id: number;
  subscriber_id: string;
  bpp_uri: string;
  organization: { name?: string; shortDesc?: string; contact_email?: string };
  status: string;
}

interface Props {
  provider: Provider | null;
}

export function CompanyProfileCard({ provider }: Props) {
  if (!provider) {
    return (
      <div style={{
        padding: 24, borderRadius: 8, background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)', textAlign: 'center',
        color: 'var(--text-tertiary)', fontSize: 13,
      }}>
        No company linked to your account
      </div>
    );
  }

  const org = provider.organization || {};
  const fields = [
    { label: 'Subscriber ID', value: provider.subscriber_id },
    { label: 'BPP URI', value: provider.bpp_uri },
    { label: 'Status', value: provider.status },
    { label: 'Contact', value: org.contact_email || '—' },
  ];

  return (
    <div style={{
      padding: '20px 22px', borderRadius: 8, background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
            {org.name || provider.subscriber_id}
          </div>
          {org.shortDesc && (
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2, fontFamily: 'var(--font-plex)' }}>{org.shortDesc}</div>
          )}
        </div>
        <div style={{
          padding: '3px 10px', borderRadius: 4,
          background: provider.status === 'active' ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.06)',
          color: provider.status === 'active' ? 'var(--trust-high)' : 'var(--trust-low)',
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
        }}>
          {provider.status.toUpperCase()}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 20px' }}>
        {fields.map(f => (
          <div key={f.label}>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em', marginBottom: 2 }}>
              {f.label.toUpperCase()}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', wordBreak: 'break-all' }}>
              {f.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
