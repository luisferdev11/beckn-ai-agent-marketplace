'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SessionDropdown } from '../../_components/shared/SessionDropdown';
import { AgentDiscovery } from '../../search/_components/AgentDiscovery';

interface User { email: string; role: string; company_name?: string }

export default function ConsumerDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.replace('/login'); return; }
    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then((u: User) => {
        // This dashboard is consumer-only. Any other role (or no role)
        // is bounced to /login rather than shown a mismatched workspace.
        if (u.role !== 'consumer') { router.replace('/login'); return; }
        setUser(u);
      })
      .catch(() => {
        localStorage.removeItem('token');
        router.replace('/login');
      });
  }, [router]);

  if (!user) return null;

  return (
    <>
      <AgentDiscovery
        header={
          <ConsumerHeader
            user={user}
            onRegister={() => setShowUpgrade(true)}
          />
        }
      />

      {/* Upgrade modal — Register Agent requires a Publisher account */}
      {showUpgrade && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
        }} onClick={() => setShowUpgrade(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: 'var(--bg-surface)', borderRadius: 10, padding: 28,
            maxWidth: 400, textAlign: 'center', boxShadow: '0 8px 40px rgba(0,0,0,0.2)',
          }}>
            <div style={{ fontSize: 24, marginBottom: 12 }}>&#x1F680;</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 8 }}>
              Publisher Account Required
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 18 }}>
              To publish agents you need a Publisher account. Would you like to upgrade your plan?
            </p>
            <a href="/upgrade" style={{
              display: 'inline-block', padding: '10px 24px', borderRadius: 6,
              background: 'var(--infosys-cobalt)', color: '#fff',
              fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
              textDecoration: 'none',
            }}>
              Upgrade Plan
            </a>
          </div>
        </div>
      )}
    </>
  );
}

// ── Authenticated consumer top bar ─────────────────────────
function ConsumerHeader({ user, onRegister }: { user: User; onRegister: () => void }) {
  return (
    <header style={{
      position: 'relative', zIndex: 20,
      borderBottom: '1px solid rgba(255,255,255,0.08)',
      background: 'rgba(0,24,53,0.5)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
    }}>
      <div style={{
        maxWidth: 1200, margin: '0 auto', padding: '0 32px',
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 0,
            fontFamily: 'var(--font-plex)', fontWeight: 700,
            fontSize: 20, letterSpacing: '-0.01em', color: '#FFFFFF',
          }}>
            <img src="/infosys-logo.png" alt="Infosys" style={{ height: 22 }} />
            <span style={{ color: 'rgba(255,255,255,0.35)', margin: '0 10px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.85)', letterSpacing: '0' }}>
              AI Agent Marketplace
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={onRegister} style={{
            padding: '6px 12px', borderRadius: 6,
            background: 'rgba(0,124,195,0.2)', border: '1px solid rgba(0,124,195,0.35)',
            color: '#7CC8F0', fontFamily: 'var(--font-plex)',
            fontSize: 12, fontWeight: 500, cursor: 'pointer',
          }}>
            Register Agent
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%', background: '#00C572',
              animation: 'pulse 2.5s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-on-dark-3)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
              BECKN v2.0 · TESTNET
            </span>
          </div>
          <SessionDropdown email={user.email} role={user.role} companyName={user.company_name} />
        </div>
      </div>
    </header>
  );
}
