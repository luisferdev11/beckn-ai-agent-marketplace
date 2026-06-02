'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { SessionDropdown } from '../../_components/shared/SessionDropdown';
import { ConformanceReport } from '../../_components/dashboard/ConformanceReport';

type Tab = 'users' | 'providers' | 'agents' | 'admissions';

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [admissions, setAdmissions] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [detail, setDetail] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (!t) { router.push('/login'); return; }
    setToken(t);

    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(setUser)
      .catch(() => router.push('/login'));
  }, [router]);

  const loadAdmissions = useCallback(async () => {
    if (!token) return;
    const res = await fetch('/api/admin/admission', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setAdmissions(await res.json());
  }, [token]);

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
    loadAdmissions();
  }, [token, loadAdmissions]);

  async function openDetail(id: number) {
    setActionError('');
    const res = await fetch(`/api/admin/admission/${id}`, { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setDetail(await res.json());
  }

  async function approveAdmission(id: number) {
    setBusy(true); setActionError('');
    const res = await fetch(`/api/admin/admission/${id}/approve`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    });
    setBusy(false);
    if (res.ok) {
      setDetail(null); await loadAdmissions();
    } else {
      const d = await res.json().catch(() => ({}));
      setActionError(d?.detail?.message || d?.error || `Approve failed (${res.status})`);
    }
  }

  async function rejectAdmission(id: number) {
    const reason = window.prompt('Reason for rejection?');
    if (!reason) return;
    setBusy(true); setActionError('');
    const res = await fetch(`/api/admin/admission/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ reason }),
    });
    setBusy(false);
    if (res.ok) { setDetail(null); await loadAdmissions(); }
    else setActionError(`Reject failed (${res.status})`);
  }

  async function retryConformance(id: number) {
    setBusy(true); setActionError('');
    await fetch(`/api/admin/admission/${id}/retry-conformance`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    });
    // The kit runs in the background; give it a moment then refetch detail.
    setTimeout(async () => { await openDetail(id); setBusy(false); }, 6000);
  }

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
            <img src="/infosys-logo.png" alt="Infosys" style={{ height: 22 }} />
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
          <button onClick={() => setTab('admissions')} style={tabStyle('admissions')}>
            BPP Admissions
            {admissions.filter(a => a.decision === 'pending').length > 0 && (
              <span style={{
                marginLeft: 6, padding: '1px 6px', borderRadius: 8, fontSize: 10, fontWeight: 700,
                fontFamily: 'var(--font-mono)', background: 'var(--infosys-cobalt)', color: '#fff',
              }}>
                {admissions.filter(a => a.decision === 'pending').length}
              </span>
            )}
          </button>
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

        {/* BPP Admissions tab */}
        {tab === 'admissions' && (
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 8, overflow: 'auto' }}>
            {admissions.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
                No BPP admission requests yet.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-elevated)' }}>
                    {['SUBSCRIBER', 'ORGANIZATION', 'JURISDICTION', 'REQUESTED', 'DECISION', 'ACTIONS'].map(h => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {admissions.map(a => (
                    <tr key={a.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ ...tdStyle, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{a.subscriber_id}</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{a.organization_data?.name || '—'}</td>
                      <td style={tdStyle}>{a.organization_data?.jurisdiction || a.jurisdiction || '—'}</td>
                      <td style={{ ...tdStyle, fontSize: 12, color: 'var(--text-tertiary)' }}>
                        {a.requested_at ? new Date(a.requested_at).toLocaleString() : '—'}
                      </td>
                      <td style={tdStyle}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                          fontFamily: 'var(--font-mono)',
                          background: a.decision === 'approved' ? 'rgba(0,135,90,0.08)' : a.decision === 'rejected' ? 'rgba(198,40,40,0.06)' : 'var(--bg-elevated)',
                          color: a.decision === 'approved' ? 'var(--trust-high)' : a.decision === 'rejected' ? 'var(--trust-low)' : 'var(--text-secondary)',
                        }}>
                          {(a.decision || 'pending').toUpperCase()}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        {actionBtn('var(--infosys-cobalt)', () => openDetail(a.id), 'Review')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      {/* Admission detail modal */}
      {detail && (
        <div
          onClick={() => setDetail(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
          }}
        >
          <div onClick={e => e.stopPropagation()} style={{
            background: 'var(--bg-surface)', borderRadius: 10, border: '1px solid var(--border-subtle)',
            padding: 28, width: '100%', maxWidth: 640, maxHeight: '90vh', overflowY: 'auto',
            boxShadow: '0 8px 40px rgba(0,0,0,0.2)',
          }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 4 }}>
              {detail.organization_data?.name || detail.subscriber_id}
            </h3>
            <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', marginBottom: 16 }}>
              {detail.subscriber_id}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 18, fontSize: 13, fontFamily: 'var(--font-plex)' }}>
              <div><span style={{ color: 'var(--text-tertiary)' }}>Contact:</span> {detail.submitted_by_email || '—'}</div>
              <div><span style={{ color: 'var(--text-tertiary)' }}>Subscriber status:</span> {detail.subscriber_status || '—'}</div>
              <div><span style={{ color: 'var(--text-tertiary)' }}>Decision:</span> {detail.decision}</div>
              <div><span style={{ color: 'var(--text-tertiary)' }}>Reviewed by:</span> {detail.reviewed_by || '—'}</div>
            </div>

            <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 8 }}>
              Conformance report
            </h4>
            <ConformanceReport conformance={detail.latest_conformance} />

            {actionError && (
              <div style={{ marginTop: 14, padding: '8px 12px', borderRadius: 6, background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)', color: 'var(--trust-low)', fontSize: 12 }}>
                {actionError}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <button onClick={() => setDetail(null)} style={{
                padding: '9px 14px', borderRadius: 6, border: '1px solid var(--border-default)',
                background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
                fontSize: 13, cursor: 'pointer',
              }}>
                Close
              </button>
              <div style={{ flex: 1 }} />
              {detail.decision === 'pending' && (
                <>
                  <button onClick={() => retryConformance(detail.id)} disabled={busy} style={{
                    padding: '9px 14px', borderRadius: 6, border: '1px solid var(--border-default)',
                    background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
                    fontSize: 13, cursor: busy ? 'not-allowed' : 'pointer',
                  }}>
                    Re-run conformance
                  </button>
                  <button onClick={() => rejectAdmission(detail.id)} disabled={busy} style={{
                    padding: '9px 14px', borderRadius: 6, border: '1px solid var(--trust-low)',
                    background: 'transparent', color: 'var(--trust-low)', fontFamily: 'var(--font-plex)',
                    fontSize: 13, fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer',
                  }}>
                    Reject
                  </button>
                  <button
                    onClick={() => approveAdmission(detail.id)}
                    disabled={busy || detail.latest_conformance?.must_passed !== true}
                    title={detail.latest_conformance?.must_passed !== true ? 'Conformance must pass before approval' : ''}
                    style={{
                      padding: '9px 18px', borderRadius: 6, border: 'none',
                      background: (busy || detail.latest_conformance?.must_passed !== true) ? 'var(--bg-elevated)' : 'var(--infosys-cobalt)',
                      color: (busy || detail.latest_conformance?.must_passed !== true) ? 'var(--text-tertiary)' : '#fff',
                      fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 600,
                      cursor: (busy || detail.latest_conformance?.must_passed !== true) ? 'not-allowed' : 'pointer',
                    }}>
                    {busy ? 'Working…' : 'Approve'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
