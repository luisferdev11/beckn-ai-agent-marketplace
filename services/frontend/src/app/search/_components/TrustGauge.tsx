'use client';

interface TrustGaugeProps {
  score: number;
  size?: number;
}

export function TrustGauge({ score }: TrustGaugeProps) {
  const color =
    score >= 90 ? 'var(--trust-high)' :
    score >= 75 ? 'var(--trust-mid)' :
    'var(--trust-low)';

  const bg =
    score >= 90 ? 'rgba(0, 135, 90, 0.08)' :
    score >= 75 ? 'rgba(201, 111, 0, 0.08)' :
    'rgba(198, 40, 40, 0.08)';

  const label =
    score >= 90 ? 'Excellent' :
    score >= 75 ? 'Good' :
    'Fair';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, flexShrink: 0 }}>
      <div style={{
        background: bg,
        border: `1px solid ${color}44`,
        borderRadius: 6,
        padding: '4px 10px',
        textAlign: 'center',
        minWidth: 46,
      }}>
        <div style={{
          fontSize: 16, fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          color, lineHeight: 1,
        }}>
          {score}
        </div>
      </div>
      <span style={{
        fontSize: 10, fontFamily: 'var(--font-plex)',
        color: 'var(--text-tertiary)', fontWeight: 500,
      }}>
        {label}
      </span>
    </div>
  );
}
