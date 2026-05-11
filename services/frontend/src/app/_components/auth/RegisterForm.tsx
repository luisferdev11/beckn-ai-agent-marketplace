'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { PasswordStrengthIndicator } from './PasswordStrengthIndicator';
import { CompanySearchForm } from './CompanySearchForm';
import { PaymentMockForm } from './PaymentMockForm';

type Role = 'consumer' | 'publisher';
type Step = 'role' | 'credentials' | 'company' | 'payment' | 'done';

export function RegisterForm() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('role');
  const [role, setRole] = useState<Role>('consumer');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // Publisher company state
  const [providerId, setProviderId] = useState<number | null>(null);
  const [showNewCompany, setShowNewCompany] = useState(false);
  const [newCompany, setNewCompany] = useState({ name: '', subscriber_id: '', bpp_uri: 'http://bpp-provider:3002' });
  const [integrationMode, setIntegrationMode] = useState<'managed' | 'external'>('managed');

  // Result state
  const [resultEmail, setResultEmail] = useState('');
  const [resultCompany, setResultCompany] = useState('');

  function validateEmail(val: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val);
  }

  function validatePassword(val: string) {
    return val.length >= 8 && /[A-Z]/.test(val) && /[0-9]/.test(val) && /[!@#$%^&*]/.test(val);
  }

  async function checkEmail() {
    if (!validateEmail(email)) {
      setErrors({ email: 'Invalid email format' });
      return false;
    }
    const res = await fetch('/api/auth/check-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const data = await res.json();
    if (data.exists) {
      setErrors({ email: 'Email already registered' });
      return false;
    }
    return true;
  }

  async function handleCredentialsNext() {
    const e: Record<string, string> = {};
    if (!validateEmail(email)) e.email = 'Invalid email format';
    if (!validatePassword(password)) e.password = 'Password does not meet requirements';
    if (password !== confirmPw) e.confirm = 'Passwords do not match';
    setErrors(e);
    if (Object.keys(e).length) return;

    // Check if email exists
    setLoading(true);
    const emailOk = await checkEmail();
    setLoading(false);
    if (!emailOk) return;

    if (role === 'publisher') {
      setStep('company');
    } else {
      await doRegister(null);
    }
  }

  function handleCompanyNext() {
    if (showNewCompany) {
      if (!newCompany.name.trim() || !newCompany.subscriber_id.trim()) {
        setErrors({ company: 'Company name and subscriber ID required' });
        return;
      }
      setErrors({});
      setStep('payment');
    } else if (providerId) {
      setErrors({});
      setStep('payment');
    } else {
      setErrors({ company: 'Select a company or create a new one' });
    }
  }

  async function doRegister(overrideProviderId: number | null) {
    setLoading(true);
    const body: Record<string, unknown> = { email, password, role };
    const finalProviderId = overrideProviderId ?? providerId;

    if (role === 'publisher') {
      body.integration_mode = integrationMode;
      if (showNewCompany) {
        body.new_provider = {
          subscriber_id: newCompany.subscriber_id,
          bpp_uri: newCompany.bpp_uri,
          organization: { name: newCompany.name },
        };
      } else if (finalProviderId) {
        body.provider_id = finalProviderId;
      }
    }

    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const data = await res.json();
      setErrors({ submit: data.error || 'Registration failed' });
      setLoading(false);
      return;
    }

    const data = await res.json();
    localStorage.setItem('token', data.token);
    setResultEmail(data.user.email);
    setResultCompany(newCompany.name || '');
    setLoading(false);
    setStep('done');
  }

  const inputStyle = (field: string) => ({
    width: '100%', padding: '10px 14px', borderRadius: 6,
    border: `1px solid ${errors[field] ? 'var(--trust-low)' : 'var(--border-default)'}`,
    background: 'var(--bg-surface)', fontFamily: 'var(--font-plex)',
    fontSize: 14, color: 'var(--text-primary)', outline: 'none',
  });

  // Step indicators
  const steps = role === 'publisher'
    ? ['Account Type', 'Credentials', 'Company', 'Payment']
    : ['Account Type', 'Credentials'];
  const stepIndex = step === 'role' ? 0 : step === 'credentials' ? 1 : step === 'company' ? 2 : step === 'payment' ? 3 : steps.length;

  return (
    <div style={{
      width: '100%', maxWidth: 480, margin: '0 auto',
      background: 'var(--bg-surface)', borderRadius: 10,
      border: '1px solid var(--border-subtle)',
      padding: '32px 28px',
      boxShadow: '0 4px 24px rgba(0,0,0,0.06)',
    }}>
      {step !== 'done' && (
        <>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 6 }}>
            Create Account
          </h2>

          {/* Step indicator */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
            {steps.map((s, i) => (
              <div key={s} style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{
                  height: 3, borderRadius: 2,
                  background: i <= stepIndex ? 'var(--infosys-cobalt)' : 'var(--bg-elevated)',
                  transition: 'background 0.3s',
                }} />
                <span style={{ fontSize: 10, color: i <= stepIndex ? 'var(--accent)' : 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
                  {s}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* STEP: Role */}
      {step === 'role' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {([
            { value: 'consumer' as Role, title: 'Consumer', price: 'Free', desc: 'Explore and hire agents from the marketplace' },
            { value: 'publisher' as Role, title: 'Publisher', price: '$29/month', desc: 'Publish your agents and monitor their performance' },
          ]).map(opt => (
            <div
              key={opt.value}
              onClick={() => setRole(opt.value)}
              style={{
                padding: '16px 18px', borderRadius: 8, cursor: 'pointer',
                border: `2px solid ${role === opt.value ? 'var(--infosys-cobalt)' : 'var(--border-subtle)'}`,
                background: role === opt.value ? 'var(--accent-dim)' : 'var(--bg-surface)',
                transition: 'all 0.15s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
                  {opt.title}
                </span>
                <span style={{
                  fontSize: 12, fontWeight: 600, fontFamily: 'var(--font-mono)',
                  color: opt.value === 'consumer' ? 'var(--trust-high)' : 'var(--infosys-cobalt)',
                  padding: '2px 8px', borderRadius: 4,
                  background: opt.value === 'consumer' ? 'rgba(0,135,90,0.08)' : 'var(--accent-dim)',
                }}>
                  {opt.price}
                </span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4, fontFamily: 'var(--font-plex)' }}>
                {opt.desc}
              </p>
            </div>
          ))}

          <button
            onClick={() => setStep('credentials')}
            style={{
              width: '100%', padding: '12px', borderRadius: 6, marginTop: 8,
              background: 'var(--infosys-cobalt)', border: 'none', color: '#fff',
              fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
              cursor: 'pointer', transition: 'all 0.2s',
            }}
          >
            Continue
          </button>
        </div>
      )}

      {/* STEP: Credentials */}
      {step === 'credentials' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" style={inputStyle('email')} />
            {errors.email && <span style={{ fontSize: 11, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)' }}>{errors.email}</span>}
          </div>

          <div>
            <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Strong password" style={inputStyle('password')} />
            {errors.password && <span style={{ fontSize: 11, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)' }}>{errors.password}</span>}
            <PasswordStrengthIndicator password={password} />
          </div>

          <div>
            <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Confirm Password</label>
            <input type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} placeholder="Confirm password" style={inputStyle('confirm')} />
            {errors.confirm && <span style={{ fontSize: 11, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)' }}>{errors.confirm}</span>}
          </div>

          {errors.submit && (
            <div style={{ padding: '8px 12px', borderRadius: 6, background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)', color: 'var(--trust-low)', fontSize: 12 }}>
              {errors.submit}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button onClick={() => setStep('role')} style={{
              flex: 1, padding: '12px', borderRadius: 6, border: '1px solid var(--border-default)',
              background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
              fontSize: 14, fontWeight: 500, cursor: 'pointer',
            }}>
              Back
            </button>
            <button onClick={handleCredentialsNext} disabled={loading} style={{
              flex: 2, padding: '12px', borderRadius: 6, border: 'none',
              background: loading ? 'var(--bg-elevated)' : 'var(--infosys-cobalt)',
              color: loading ? 'var(--text-tertiary)' : '#fff', fontFamily: 'var(--font-plex)',
              fontSize: 14, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
            }}>
              {loading ? 'Checking...' : role === 'publisher' ? 'Continue' : 'Create Account'}
            </button>
          </div>
        </div>
      )}

      {/* STEP: Company (publisher only) */}
      {step === 'company' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
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
                }}>
                  Back to search
                </button>
              </div>
              <input value={newCompany.name} onChange={e => setNewCompany(p => ({ ...p, name: e.target.value }))} placeholder="Company name" style={inputStyle('company')} />
              <input value={newCompany.subscriber_id} onChange={e => setNewCompany(p => ({ ...p, subscriber_id: e.target.value }))} placeholder="Subscriber ID (e.g. my-company.beckn)" style={inputStyle('company')} />
            </div>
          )}

          {errors.company && <span style={{ fontSize: 11, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)' }}>{errors.company}</span>}

          {/* Integration mode selector */}
          <div style={{ marginTop: 8 }}>
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

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button onClick={() => setStep('credentials')} style={{
              flex: 1, padding: '12px', borderRadius: 6, border: '1px solid var(--border-default)',
              background: 'var(--bg-surface)', color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
              fontSize: 14, fontWeight: 500, cursor: 'pointer',
            }}>
              Back
            </button>
            <button onClick={handleCompanyNext} style={{
              flex: 2, padding: '12px', borderRadius: 6, border: 'none',
              background: 'var(--infosys-cobalt)', color: '#fff', fontFamily: 'var(--font-plex)',
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}>
              Continue to Payment
            </button>
          </div>
        </div>
      )}

      {/* STEP: Payment (publisher only) */}
      {step === 'payment' && (
        <div>
          <PaymentMockForm onSuccess={() => doRegister(null)} />

          <button onClick={() => setStep('company')} style={{
            width: '100%', marginTop: 12, padding: '10px', borderRadius: 6,
            border: '1px solid var(--border-default)', background: 'var(--bg-surface)',
            color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', fontSize: 13, cursor: 'pointer',
          }}>
            Back
          </button>

          {errors.submit && (
            <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 6, background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)', color: 'var(--trust-low)', fontSize: 12 }}>
              {errors.submit}
            </div>
          )}
        </div>
      )}

      {/* STEP: Done */}
      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>&#10003;</div>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 6 }}>
            Welcome!
          </h2>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4 }}>
            {role === 'publisher' ? `Company: ${resultCompany || 'Linked'}` : resultEmail}
          </p>
          <div style={{
            display: 'inline-block', padding: '3px 10px', borderRadius: 4, marginBottom: 16,
            background: role === 'publisher' ? 'var(--accent-dim)' : 'rgba(0,135,90,0.08)',
            color: role === 'publisher' ? 'var(--infosys-cobalt)' : 'var(--trust-high)',
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600,
          }}>
            {role.toUpperCase()}
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Redirecting to dashboard...</p>
          {(() => { setTimeout(() => router.push('/dashboard'), 2000); return null; })()}
        </div>
      )}

      {/* Link to login */}
      {step !== 'done' && (
        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <span style={{ fontSize: 13, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
            Already have an account?{' '}
            <a href="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 500 }}>Sign in</a>
          </span>
        </div>
      )}
    </div>
  );
}
