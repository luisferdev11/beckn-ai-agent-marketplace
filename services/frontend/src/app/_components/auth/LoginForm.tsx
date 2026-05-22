'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) { setError('Email and password required'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Invalid email format'); return; }

    setLoading(true);
    setError('');

    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const data = await res.json();
      setError(data.error || 'Login failed');
      setLoading(false);
      return;
    }

    const data = await res.json();
    localStorage.setItem('token', data.token);
    router.push('/dashboard');
  }

  const inputStyle = {
    width: '100%', padding: '10px 14px', borderRadius: 6,
    border: '1px solid var(--border-default)', background: 'var(--bg-surface)',
    fontFamily: 'var(--font-plex)', fontSize: 14, color: 'var(--text-primary)', outline: 'none',
  };

  return (
    <div style={{
      width: '100%', maxWidth: 420, margin: '0 auto',
      background: 'var(--bg-surface)', borderRadius: 10,
      border: '1px solid var(--border-subtle)',
      padding: '32px 28px',
      boxShadow: '0 4px 24px rgba(0,0,0,0.06)',
    }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 20 }}>
        Sign In
      </h2>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Email</label>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" style={inputStyle} />
        </div>

        <div>
          <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Password</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" style={inputStyle} />
        </div>

        {error && (
          <div style={{
            padding: '8px 12px', borderRadius: 6,
            background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)',
            color: 'var(--trust-low)', fontSize: 12, fontFamily: 'var(--font-plex)',
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} style={{
          width: '100%', padding: '12px', borderRadius: 6, border: 'none',
          background: loading ? 'var(--bg-elevated)' : 'var(--infosys-cobalt)',
          color: loading ? 'var(--text-tertiary)' : '#fff',
          fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
          cursor: loading ? 'not-allowed' : 'pointer', transition: 'all 0.2s', marginTop: 4,
        }}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>

      <div style={{ textAlign: 'center', marginTop: 20 }}>
        <span style={{ fontSize: 13, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
          {"Don't have an account? "}
          <a href="/register" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}>Create one</a>
        </span>
      </div>
    </div>
  );
}
