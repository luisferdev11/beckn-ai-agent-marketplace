'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface Props {
  email: string;
  role: string;
  companyName?: string | null;
}

export function SessionDropdown({ email, role, companyName }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  async function logout() {
    localStorage.removeItem('token');
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  }

  const initial = email[0].toUpperCase();
  const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px 8px', borderRadius: 6,
        }}
      >
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'var(--infosys-cobalt)', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
        }}>
          {initial}
        </div>
        <div style={{ textAlign: 'left' }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', lineHeight: 1.2 }}>
            {companyName || email.split('@')[0]}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
            ({roleLabel})
          </div>
        </div>
        <svg width="12" height="12" viewBox="0 0 12 12" style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <path d="M3 5L6 8L9 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div style={{
          position: 'absolute', right: 0, top: '100%', marginTop: 6,
          background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
          borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          minWidth: 180, overflow: 'hidden', zIndex: 100,
          animation: 'slideDown 0.15s ease-out',
        }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>{email}</div>
          </div>
          <button
            onClick={logout}
            style={{
              width: '100%', padding: '10px 14px', background: 'transparent',
              border: 'none', textAlign: 'left', cursor: 'pointer',
              fontFamily: 'var(--font-plex)', fontSize: 13, color: 'var(--trust-low)',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-elevated)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            Sign Out
          </button>
        </div>
      )}
    </div>
  );
}
