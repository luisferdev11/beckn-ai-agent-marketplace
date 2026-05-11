'use client';

interface StatItem {
  agent_id: number;
  name: string;
  label: string;
  total_queries: number;
  unique_users: number;
  week_queries: number;
  last_used_at: string | null;
}

interface Props {
  stats: StatItem[];
}

export function AgentStatsCard({ stats }: Props) {
  if (!stats.length) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13, fontFamily: 'var(--font-plex)' }}>
        No agent statistics yet
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 14 }}>
      {stats.map(s => (
        <div key={s.agent_id} style={{
          padding: '18px', borderRadius: 8, background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 12 }}>
            {s.label || s.name}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--infosys-cobalt)', fontFamily: 'var(--font-plex)' }}>{s.total_queries}</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>TOTAL QUERIES</div>
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>{s.unique_users}</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>UNIQUE USERS</div>
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--trust-high)', fontFamily: 'var(--font-plex)' }}>{s.week_queries}</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>THIS WEEK</div>
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginTop: 4 }}>
                {s.last_used_at ? new Date(s.last_used_at).toLocaleDateString() : '—'}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>LAST USED</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
