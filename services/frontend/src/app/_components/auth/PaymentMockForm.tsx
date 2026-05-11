'use client';

import { useState } from 'react';

interface Props {
  onSuccess: () => void;
}

function formatCardNumber(val: string) {
  return val.replace(/\D/g, '').slice(0, 16).replace(/(.{4})/g, '$1 ').trim();
}

function formatExpiry(val: string) {
  const digits = val.replace(/\D/g, '').slice(0, 4);
  if (digits.length > 2) return digits.slice(0, 2) + '/' + digits.slice(2);
  return digits;
}

export function PaymentMockForm({ onSuccess }: Props) {
  const [card, setCard] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvv, setCvv] = useState('');
  const [name, setName] = useState('');
  const [processing, setProcessing] = useState(false);
  const [done, setDone] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate() {
    const e: Record<string, string> = {};
    if (card.replace(/\s/g, '').length !== 16) e.card = 'Card number must be 16 digits';
    if (!/^\d{2}\/\d{2}$/.test(expiry)) e.expiry = 'Format: MM/YY';
    if (!/^\d{3}$/.test(cvv)) e.cvv = 'CVV must be 3 digits';
    if (!name.trim()) e.name = 'Name required';
    setErrors(e);
    return !Object.keys(e).length;
  }

  function handleSubmit() {
    if (!validate()) return;
    setProcessing(true);
    setTimeout(() => {
      setProcessing(false);
      setDone(true);
      setTimeout(onSuccess, 1500);
    }, 1500);
  }

  if (done) {
    return (
      <div style={{
        textAlign: 'center', padding: '24px',
        background: 'rgba(0,135,90,0.06)', border: '1px solid rgba(0,135,90,0.2)',
        borderRadius: 8,
      }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>&#10003;</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--trust-high)', fontFamily: 'var(--font-plex)' }}>
          Payment successful!
        </div>
      </div>
    );
  }

  const inputStyle = (field: string) => ({
    width: '100%', padding: '10px 14px', borderRadius: 6,
    border: `1px solid ${errors[field] ? 'var(--trust-low)' : 'var(--border-default)'}`,
    background: 'var(--bg-surface)', fontFamily: 'var(--font-plex)',
    fontSize: 14, color: 'var(--text-primary)', outline: 'none',
  });

  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 16 }}>
        Publisher Subscription — $29/month
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Card Number</label>
          <input value={card} onChange={e => setCard(formatCardNumber(e.target.value))} placeholder="1234 5678 9012 3456" style={inputStyle('card')} />
          {errors.card && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.card}</span>}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Expiry</label>
            <input value={expiry} onChange={e => setExpiry(formatExpiry(e.target.value))} placeholder="MM/YY" style={inputStyle('expiry')} />
            {errors.expiry && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.expiry}</span>}
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>CVV</label>
            <input value={cvv} onChange={e => setCvv(e.target.value.replace(/\D/g, '').slice(0, 3))} placeholder="123" style={inputStyle('cvv')} />
            {errors.cvv && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.cvv}</span>}
          </div>
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 4, display: 'block' }}>Name on Card</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="John Doe" style={inputStyle('name')} />
          {errors.name && <span style={{ fontSize: 11, color: 'var(--trust-low)' }}>{errors.name}</span>}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={processing}
        style={{
          width: '100%', marginTop: 18, padding: '12px', borderRadius: 6,
          background: processing ? 'var(--bg-elevated)' : 'var(--infosys-cobalt)',
          border: 'none', color: processing ? 'var(--text-tertiary)' : '#fff',
          fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
          cursor: processing ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s',
        }}
      >
        {processing ? (
          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <span style={{ width: 14, height: 14, border: '2px solid var(--border-default)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', display: 'inline-block' }} />
            Processing...
          </span>
        ) : 'Subscribe — $29/month'}
      </button>
    </div>
  );
}
