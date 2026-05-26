import Link from 'next/link';

export default function ForbiddenPage() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      padding: 24,
    }}>
      <div style={{ fontSize: 48, fontWeight: 700, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
        403
      </div>
      <h1 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 8 }}>
        Access Denied
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 24, maxWidth: 400 }}>
        You do not have permission to access this page. Please contact your administrator if you believe this is a mistake.
      </p>
      <Link href="/dashboard" style={{
        padding: '10px 24px', borderRadius: 6,
        background: 'var(--infosys-cobalt)', color: '#fff',
        fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
        textDecoration: 'none',
      }}>
        Go to Dashboard
      </Link>
    </div>
  );
}
