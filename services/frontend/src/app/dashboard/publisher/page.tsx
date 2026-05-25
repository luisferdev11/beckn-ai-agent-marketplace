'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { SessionDropdown } from '../../_components/shared/SessionDropdown';
import { CompanyProfileCard } from '../../_components/dashboard/CompanyProfileCard';
import { AgentStatsCard } from '../../_components/dashboard/AgentStatsCard';
import { RegisterAgentForm } from '../../_components/dashboard/RegisterAgentForm';

interface User { id: string; email: string; role: string; company_name?: string; provider_id: number | null }

export default function PublisherDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [provider, setProvider] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [agents, setAgents] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [stats, setStats] = useState<any[]>([]);
  const [showNewAgent, setShowNewAgent] = useState(false);

  const loadData = useCallback(async (t: string, providerId: number | null) => {
    const headers = { Authorization: `Bearer ${t}` };
    const [agentsRes, statsRes] = await Promise.all([
      fetch('/api/publisher/agents', { headers }),
      fetch('/api/publisher/stats', { headers }),
    ]);
    if (agentsRes.ok) setAgents(await agentsRes.json());
    if (statsRes.ok) setStats(await statsRes.json());

    if (providerId) {
      const provRes = await fetch('/api/providers');
      if (provRes.ok) {
        const providers = await provRes.json();
        setProvider(providers.find((p: { id: number }) => p.id === providerId) || null);
      }
    }
  }, []);

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (!t) { router.push('/login'); return; }
    setToken(t);

    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(u => {
        setUser(u);
        loadData(t, u.provider_id);
      })
      .catch(() => router.push('/login'));
  }, [router, loadData]);

  if (!user) return null;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-content)' }}>
      {/* Header */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 50,
        borderBottom: '1px solid var(--border-subtle)',
        background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(12px)',
      }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto', padding: '0 32px',
          height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <img src="/infosys-logo.png" alt="Infosys" style={{ height: 22 }} />
            <span style={{ color: 'var(--border-strong)', margin: '0 4px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>Publisher Portal</span>
          </div>
          <SessionDropdown email={user.email} role={user.role} companyName={user.company_name} />
        </div>
      </header>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px' }}>
        {/* Company section */}
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 12 }}>
            My Company
          </h2>
          <CompanyProfileCard provider={provider} />
        </section>

        {/* Agents section */}
        <section style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
              My Agents
            </h2>
            <button onClick={() => setShowNewAgent(true)} style={{
              padding: '7px 14px', borderRadius: 6, border: 'none',
              background: 'var(--infosys-cobalt)', color: '#fff',
              fontFamily: 'var(--font-plex)', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>
              + Register New Agent
            </button>
          </div>

          {agents.length === 0 ? (
            <div style={{
              padding: 32, textAlign: 'center', background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)', borderRadius: 8,
              color: 'var(--text-tertiary)', fontSize: 13,
            }}>
              No agents registered yet
            </div>
          ) : (
            <div style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
              borderRadius: 8, overflow: 'hidden',
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-plex)', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-subtle)' }}>
                    {['Name', 'Category', 'Status', 'Queries', 'Last Used'].map(h => (
                      <th key={h} style={{
                        padding: '10px 14px', textAlign: 'left', fontWeight: 600,
                        color: 'var(--text-secondary)', fontSize: 11,
                        fontFamily: 'var(--font-mono)', letterSpacing: '0.04em',
                      }}>
                        {h.toUpperCase()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a: Record<string, string | number | null>) => (
                    <tr key={a.id as number} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 500, color: 'var(--text-primary)' }}>
                        {(a.label as string) || (a.agent_name as string) || `Agent #${a.id}`}
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>{a.category_name || '—'}</td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                          fontFamily: 'var(--font-mono)',
                          background: a.status === 'active' ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.06)',
                          color: a.status === 'active' ? 'var(--trust-high)' : 'var(--trust-low)',
                        }}>
                          {(a.status as string || '').toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                        {a.total_queries ?? 0}
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--text-tertiary)', fontSize: 12 }}>
                        {a.last_used_at ? new Date(a.last_used_at as string).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Stats section */}
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 12 }}>
            Statistics
          </h2>
          <AgentStatsCard stats={stats} />
        </section>
      </div>

      {showNewAgent && (
        <RegisterAgentForm
          token={token}
          onSuccess={() => { setShowNewAgent(false); loadData(token, user.provider_id); }}
          onCancel={() => setShowNewAgent(false)}
        />
      )}
    </div>
  );
}
