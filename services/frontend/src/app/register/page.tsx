'use client';

import { RegisterForm } from '../_components/auth/RegisterForm';

export default function RegisterPage() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-surface)',
      }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto', padding: '0 32px',
          height: 60, display: 'flex', alignItems: 'center',
        }}>
          <a href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
            <img src="/infosys-logo.png" alt="Infosys" style={{ height: 22 }} />
            <span style={{ color: 'var(--border-strong)', margin: '0 10px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>AI Agent Marketplace</span>
          </a>
        </div>
      </header>

      {/* Content */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
        <RegisterForm />
      </div>
    </div>
  );
}
