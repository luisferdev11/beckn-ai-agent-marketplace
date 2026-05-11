'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { PaymentMockForm } from '../_components/auth/PaymentMockForm';
import { CompanySearchForm } from '../_components/auth/CompanySearchForm';

export default function UpgradePage() {
  const router = useRouter();
  const [step, setStep] = useState<'company' | 'payment' | 'done'>('company');
  const [providerId, setProviderId] = useState<number | null>(null);
  const [showNewCompany, setShowNewCompany] = useState(false);
  const [newCompany, setNewCompany] = useState({ name: '', subscriber_id: '', bpp_uri: 'http://bpp-provider:3002' });
  const [integrationMode, setIntegrationMode] = useState<'managed' | 'external'>('managed');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) router.push('/login');
  }, [router]);

  function handleCompanyNext() {
    if (showNewCompany) {
      if (!newCompany.name.trim() || !newCompany.subscriber_id.trim()) {
        setErrors({ company: 'Company name and subscriber ID required' });
        return;
      }
    } else if (!providerId) {
      setErrors({ company: 'Select a company or create a new one' });
      return;
    }
    setErrors({});
    setStep('payment');
  }

  async function handleUpgrade() {
    setLoading(true);
    const token = localStorage.getItem('token');

    // Build the upgrade request
    const body: Record<string, unknown> = { integration_mode: integrationMode };
    if (showNewCompany) {
      body.new_provider = {
        subscriber_id: newCompany.subscriber_id,
        bpp_uri: newCompany.bpp_uri,
        organization: { name: newCompany.name },
      };
    } else if (providerId) {
      body.provider_id = providerId;
    }

    const res = await fetch('/api/auth/upgrade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });

    setLoading(false);
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('token', data.token);
      setStep('done');
      setTimeout(() => router.push('/dashboard'), 2000);
    } else {
      const data = await res.json();
      setErrors({ submit: data.error || 'Upgrade failed' });
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{
        borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-surface)',
      }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto', padding: '0 32px',
          height: 60, display: 'flex', alignItems: 'center',
        }}>
          <a href="/dashboard" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
            <span style={{ color: 'var(--infosys-cobalt)', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 20 }}>Infosys</span>
            <span style={{ color: 'var(--border-strong)', margin: '0 10px', fontWeight: 300 }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>Upgrade to Publisher</span>
          </a>
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
        <div style={{
          width: '100%', maxWidth: 480, background: 'var(--bg-surface)', borderRadius: 10,
          border: '1px solid var(--border-subtle)', padding: '32px 28px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.06)',
        }}>
          {step !== 'done' && (
            <>
              <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 4 }}>
                Upgrade to Publisher
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 20 }}>
                Publish your AI agents and monitor their performance — $29/month
              </p>

              <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
                {['Company', 'Payment'].map((s, i) => (
                  <div key={s} style={{ flex: 1 }}>
                    <div style={{
                      height: 3, borderRadius: 2, marginBottom: 4,
                      background: i <= (step === 'company' ? 0 : 1) ? 'var(--infosys-cobalt)' : 'var(--bg-elevated)',
                      transition: 'background 0.3s',
                    }} />
                    <span style={{ fontSize: 10, color: i <= (step === 'company' ? 0 : 1) ? 'var(--accent)' : 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
                      {s}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {step === 'company' && (
            <div>
              {!showNewCompany ? (
                <CompanySearchForm
                  selectedId={providerId}
                  onSelect={id => { setProviderId(id); setShowNewCompany(false); }}
                  onCreateNew={() => setShowNewCompany(true)}
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>New Company</span>
                    <button onClick={() => setShowNewCompany(false)} style={{
                      background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', fontFamily: 'var(--font-plex)',
                    }}>Back to search</button>
                  </div>
                  <input value={newCompany.name} onChange={e => setNewCompany(p => ({ ...p, name: e.target.value }))} placeholder="Company name"
                    style={{ width: '100%', padding: '10px 14px', borderRadius: 6, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', fontFamily: 'var(--font-plex)', fontSize: 14, color: 'var(--text-primary)', outline: 'none' }} />
                  <input value={newCompany.subscriber_id} onChange={e => setNewCompany(p => ({ ...p, subscriber_id: e.target.value }))} placeholder="Subscriber ID (e.g. my-company.beckn)"
                    style={{ width: '100%', padding: '10px 14px', borderRadius: 6, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', fontFamily: 'var(--font-plex)', fontSize: 14, color: 'var(--text-primary)', outline: 'none' }} />
                </div>
              )}

              {errors.company && <span style={{ fontSize: 11, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)', display: 'block', marginTop: 8 }}>{errors.company}</span>}

              {/* Integration mode selector */}
              <div style={{ marginTop: 12 }}>
                <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 8, display: 'block' }}>
                  How will your agents run?
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  {([
                    { value: 'managed' as const, title: 'Managed', desc: 'We run your agents. You provide an API key.' },
                    { value: 'external' as const, title: 'External', desc: 'You host your own endpoint. We call your URL.' },
                  ]).map(opt => (
                    <div
                      key={opt.value}
                      onClick={() => setIntegrationMode(opt.value)}
                      style={{
                        flex: 1, padding: '12px 14px', borderRadius: 8, cursor: 'pointer',
                        border: `2px solid ${integrationMode === opt.value ? 'var(--infosys-cobalt)' : 'var(--border-subtle)'}`,
                        background: integrationMode === opt.value ? 'var(--accent-dim)' : 'var(--bg-surface)',
                        transition: 'all 0.15s',
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>{opt.title}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)', marginTop: 2 }}>{opt.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                <a href="/dashboard" style={{
                  flex: 1, padding: '12px', borderRadius: 6, border: '1px solid var(--border-default)',
                  background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
                  fontSize: 14, fontWeight: 500, textDecoration: 'none', textAlign: 'center',
                }}>Cancel</a>
                <button onClick={handleCompanyNext} style={{
                  flex: 2, padding: '12px', borderRadius: 6, border: 'none',
                  background: 'var(--infosys-cobalt)', color: '#fff', fontFamily: 'var(--font-plex)',
                  fontSize: 14, fontWeight: 600, cursor: 'pointer',
                }}>Continue to Payment</button>
              </div>
            </div>
          )}

          {step === 'payment' && (
            <div>
              <PaymentMockForm onSuccess={handleUpgrade} />
              <button onClick={() => setStep('company')} style={{
                width: '100%', marginTop: 12, padding: '10px', borderRadius: 6,
                border: '1px solid var(--border-default)', background: 'var(--bg-surface)',
                color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', fontSize: 13, cursor: 'pointer',
              }}>Back</button>
              {loading && <div style={{ textAlign: 'center', marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>Upgrading account...</div>}
              {errors.submit && <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 6, background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)', color: 'var(--trust-low)', fontSize: 12 }}>{errors.submit}</div>}
            </div>
          )}

          {step === 'done' && (
            <div style={{ textAlign: 'center', padding: '16px 0' }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>&#10003;</div>
              <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 6 }}>
                Upgrade Complete!
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4 }}>
                You are now a Publisher. Redirecting to dashboard...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
