'use client';

interface Props {
  password: string;
}

const RULES = [
  { label: 'At least 8 characters', test: (p: string) => p.length >= 8 },
  { label: 'At least 1 uppercase', test: (p: string) => /[A-Z]/.test(p) },
  { label: 'At least 1 number', test: (p: string) => /[0-9]/.test(p) },
  { label: 'At least 1 special char (!@#$%^&*)', test: (p: string) => /[!@#$%^&*]/.test(p) },
];

export function PasswordStrengthIndicator({ password }: Props) {
  const passed = RULES.filter(r => r.test(password)).length;
  const ratio = passed / RULES.length;
  const color = ratio <= 0.25 ? 'var(--trust-low)' : ratio <= 0.5 ? 'var(--trust-mid)' : ratio < 1 ? 'var(--trust-mid)' : 'var(--trust-high)';

  if (!password) return null;

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{
        height: 4, borderRadius: 2, background: 'var(--bg-elevated)',
        overflow: 'hidden', marginBottom: 8,
      }}>
        <div style={{
          height: '100%', borderRadius: 2, background: color,
          width: `${ratio * 100}%`, transition: 'all 0.3s',
        }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {RULES.map(rule => (
          <div key={rule.label} style={{
            fontSize: 12, fontFamily: 'var(--font-plex)',
            color: rule.test(password) ? 'var(--trust-high)' : 'var(--text-tertiary)',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ fontSize: 10 }}>{rule.test(password) ? '✓' : '○'}</span>
            {rule.label}
          </div>
        ))}
      </div>
    </div>
  );
}
