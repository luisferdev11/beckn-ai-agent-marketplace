import Link from 'next/link';

export default function LandingPage() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        position: 'relative', zIndex: 10,
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(0,24,53,0.5)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto', padding: '0 32px',
          height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ color: '#007CC3', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 20 }}>Infosys</span>
            <span style={{ color: 'rgba(255,255,255,0.35)', margin: '0 10px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.85)', fontFamily: 'var(--font-plex)' }}>AI Agent Marketplace</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Link href="/login" style={{
              padding: '7px 16px', borderRadius: 6,
              border: '1px solid rgba(255,255,255,0.2)', background: 'transparent',
              color: '#fff', fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 500,
              textDecoration: 'none', transition: 'all 0.15s',
            }}>
              Sign In
            </Link>
            <Link href="/register" style={{
              padding: '7px 16px', borderRadius: 6, border: 'none',
              background: 'var(--infosys-cobalt)', color: '#fff',
              fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 600,
              textDecoration: 'none', transition: 'all 0.2s',
              boxShadow: '0 2px 10px rgba(0,124,195,0.35)',
            }}>
              Create Account
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="hero-gradient" style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '0 24px 80px', textAlign: 'center',
      }}>
        {/* Eyebrow */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '5px 14px', borderRadius: 4,
          background: 'rgba(0,124,195,0.2)', border: '1px solid rgba(0,124,195,0.35)',
          marginBottom: 24, animation: 'fadeInUp 0.4s ease-out both',
        }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#007CC3', flexShrink: 0 }} />
          <span style={{ fontSize: 12, fontWeight: 500, color: '#7CC8F0', fontFamily: 'var(--font-plex)', letterSpacing: '0.04em' }}>
            Enterprise AI Platform · Powered by Beckn Protocol
          </span>
        </div>

        {/* Heading */}
        <h1 style={{
          fontFamily: 'var(--font-plex)', fontSize: 'clamp(28px, 3.8vw, 46px)',
          fontWeight: 600, color: '#FFFFFF', lineHeight: 1.15,
          letterSpacing: '-0.02em', marginBottom: 14, maxWidth: 640,
          animation: 'fadeInUp 0.4s ease-out 0.07s both',
        }}>
          Find the right AI agent<br />
          <span style={{ color: '#7CC8F0', fontWeight: 300 }}>for your business task</span>
        </h1>

        {/* Subtitle */}
        <p style={{
          fontSize: 15, color: 'var(--text-on-dark-2)', fontFamily: 'var(--font-plex)',
          marginBottom: 36, maxWidth: 480, lineHeight: 1.65, fontWeight: 400,
          animation: 'fadeInUp 0.4s ease-out 0.13s both',
        }}>
          Discover, evaluate, and deploy verified AI agents on the open Beckn network.
          Ed25519 signed and DeDi verified. Publish your own agents and monitor their performance.
        </p>

        {/* CTAs */}
        <div style={{
          display: 'flex', gap: 14, animation: 'fadeInUp 0.4s ease-out 0.20s both',
        }}>
          <Link href="/register" style={{
            padding: '12px 28px', borderRadius: 6, border: 'none',
            background: 'var(--infosys-cobalt)', color: '#fff',
            fontFamily: 'var(--font-plex)', fontSize: 15, fontWeight: 600,
            textDecoration: 'none', transition: 'all 0.2s',
            boxShadow: '0 4px 20px rgba(0,124,195,0.4)',
          }}>
            Create Account
          </Link>
          <Link href="/login" style={{
            padding: '12px 28px', borderRadius: 6,
            border: '1px solid rgba(255,255,255,0.25)', background: 'rgba(255,255,255,0.06)',
            color: '#fff', fontFamily: 'var(--font-plex)', fontSize: 15, fontWeight: 500,
            textDecoration: 'none', transition: 'all 0.15s',
          }}>
            Sign In
          </Link>
        </div>

        {/* Stats */}
        <div style={{
          display: 'flex', gap: 0, marginTop: 48,
          borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 28,
          animation: 'fadeInUp 0.4s ease-out 0.28s both',
        }}>
          {[
            { value: 'Ed25519', label: 'Signed Transactions' },
            { value: 'DeDi', label: 'Verified Registry' },
            { value: 'Beckn v2.0', label: 'Protocol Version' },
          ].map((stat, i) => (
            <div key={stat.label} style={{
              textAlign: 'center', padding: '0 28px',
              borderRight: i < 2 ? '1px solid rgba(255,255,255,0.1)' : 'none',
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#FFFFFF', fontFamily: 'var(--font-plex)' }}>{stat.value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-on-dark-3)', fontFamily: 'var(--font-plex)', marginTop: 3, letterSpacing: '0.03em' }}>{stat.label}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
