'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function DashboardRouter() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }

    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(user => {
        if (user.role === 'admin') router.replace('/dashboard/admin');
        else if (user.role === 'publisher') router.replace('/dashboard/publisher');
        else router.replace('/dashboard/consumer');
      })
      .catch(() => {
        localStorage.removeItem('token');
        router.push('/login');
      })
      .finally(() => setChecking(false));
  }, [router]);

  if (checking) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          width: 20, height: 20, border: '2px solid var(--border-default)',
          borderTopColor: 'var(--accent)', borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
      </div>
    );
  }

  return null;
}
