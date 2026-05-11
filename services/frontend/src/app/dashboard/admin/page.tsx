'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SessionDropdown } from '../../_components/shared/SessionDropdown';

type Tab = 'users' | 'providers' | 'agents';

interface User { id: string; email: string; role: string; company_name?: string }

export default function AdminDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState('');
  const [tab, setTab] = useState<Tab>('users');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [users, setUsers] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [providers, setProviders] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [agents, setAgents] = useState<any[]>([]);

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (!t) { router.push('/login'); return; }
    setToken(t);

    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(setUser)
      .catch(() => router.push('/login'));
  }, [router]);

  useEffect(() => {
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch('/api/admin/users', { headers }).then(r => r.json()),
      fetch('/api/admin/providers', { headers }).then(r => r.json()),
      fetch('/api/admin/agents', { headers }).then(r => r.json()),
    ]).then(([u, p, a]) => {
      setUsers(u); setProviders(p); setAgents(a);
    });
  }, [token]);

  async function updateUser(id: string, field: string, value: string) {
    await fetch('/api/admin/users', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ id, [field]: value }),
    });
    const res = await fetch('/api/admin/users', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setUsers(await res.json());
  }

  async function updateProvider(id: number, status: string) {
    await fetch('/api/admin/providers', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ id, status }),
    });
    const res = await fetch('/api/admin/providers', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setProviders(await res.json());
  }

  async function updateAgent(id: number, status: string) {
    await fetch('/api/admin/agents', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ id, status }),
    });
    const res = await fetch('/api/admin/agents', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setAgents(await res.json());
  }

  if (!user) return null;

  const tabStyle = (t: Tab) => ({
    padding: '8px 18px', borderRadius: '6px 6px 0 0', border: 'none',
    background: tab === t ? 'var(--bg-surface)' : 'transparent',
    color: tab === t ? 'var(--infosys-cobalt)' : 'var(--text-tertiary)',
    fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: tab === t ? 600 : 400,
    cursor: 'pointer', borderBottom: tab === t ? '2px solid var(--infosys-cobalt)' : '2px solid transparent',
    transition: 'all 0.15s',
  });

  const thStyle = {
    padding: '10px 14px', textAlign: 'left' as const, fontWeight: 600,
    color: 'var(--text-secondary)', fontSize: 11,
    fontFamily: 'var(--font-mono)', letterSpacing: '0.04em',
  };

  const tdStyle = { padding: '10px 14px', fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' };

  const actionBtn = (color: string, onClick: () => void, label: string) => (
    <button onClick={onClick} style={{
      padding: '3px 8px', borderRadius: 4, border: '1px solid ' + color,
      background: 'transparent', color, fontSize: 11, fontWeight: 500,
      fontFamily: 'var(--font-plex)', cursor: 'pointer',
    }}>
      {label}
    </button>
  );

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
            <span style={{ color: 'var(--infosys-cobalt)', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 20 }}>Infosys</span>
            <span style={{ color: 'var(--border-strong)', margin: '0 4px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>Admin Panel</span>
          </div>
          <SessionDropdown email={user.email} role={user.role} />
        </div>
      </header>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 32px' }}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-subtle)', marginBottom: 20 }}>
          <button onClick={() => setTab('users')} style={tabStyle('users')}>Users</button>
          <button onClick={() => setTab('providers')} style={tabStyle('providers')}>Companies</button>
          <button onClick={() => setTab('agents')} style={tabStyle('agents')}>Agents</button>
        </div>

        {/* Users tab */}
        {tab === 'users' && (
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 8, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--bg-elevated)' }}>
                  {['EMAIL', 'ROLE', 'SUBSCRIPTION', 'COMPANY', 'REGISTERED', 'ACTIONS'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={tdStyle}>{u.email}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        background: u.role === 'admin' ? 'rgba(198,40,40,0.06)' : u.role === 'publisher' ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                        color: u.role === 'admin' ? 'var(--trust-low)' : u.role === 'publisher' ? 'var(--infosys-cobalt)' : 'var(--text-secondary)',
                      }}>
                        {u.role.toUpperCase()}
                      </span>
                    </td>
                    <td style={tdStyle}>{u.subscription_status}</td>
                    <td style={tdStyle}>{u.company_name || '—'}</td>
                    <td style={{ ...tdStyle, fontSize: 12, color: 'var(--text-tertiary)' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {u.role === 'consumer' && actionBtn('var(--infosys-cobalt)', () => updateUser(u.id, 'role', 'publisher'), 'Make Publisher')}
                        {u.role === 'publisher' && actionBtn('var(--text-secondary)', () => updateUser(u.id, 'role', 'consumer'), 'Make Consumer')}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Providers tab */}
        {tab === 'providers' && (
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 8, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--bg-elevated)' }}>
                  {['ID', 'NAME', 'SUBSCRIBER ID', 'STATUS', 'PUBLISHERS', 'ACTIONS'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {providers.map(p => (
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }}>{p.id}</td>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{p.organization?.name || '—'}</td>
                    <td style={{ ...tdStyle, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{p.subscriber_id}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        background: p.status === 'active' ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.06)',
                        color: p.status === 'active' ? 'var(--trust-high)' : 'var(--trust-low)',
                      }}>
                        {p.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }}>{p.publisher_count}</td>
                    <td style={tdStyle}>
                      {p.status === 'active'
                        ? actionBtn('var(--trust-low)', () => updateProvider(p.id, 'inactive'), 'Deactivate')
                        : actionBtn('var(--trust-high)', () => updateProvider(p.id, 'active'), 'Activate')
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Agents tab */}
        {tab === 'agents' && (
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 8, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--bg-elevated)' }}>
                  {['NAME', 'CATEGORY', 'COMPANY', 'STATUS', 'QUERIES', 'ACTIONS'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ ...tdStyle, fontWeight: 500 }}>{a.label || a.name || `#${a.id}`}</td>
                    <td style={tdStyle}>{a.category_name || '—'}</td>
                    <td style={tdStyle}>{a.company_name || '—'}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        background: a.status === 'active' ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.06)',
                        color: a.status === 'active' ? 'var(--trust-high)' : 'var(--trust-low)',
                      }}>
                        {a.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }}>{a.total_queries}</td>
                    <td style={tdStyle}>
                      {a.status === 'active'
                        ? actionBtn('var(--trust-low)', () => updateAgent(a.id, 'inactive'), 'Deactivate')
                        : actionBtn('var(--trust-high)', () => updateAgent(a.id, 'active'), 'Activate')
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
