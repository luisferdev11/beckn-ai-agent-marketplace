'use client';

/**
 * ScoreBreakdown — visual breakdown of the composite discover score.
 *
 * The marketplace ranks agents with:
 *
 *     score = 0.5·semantic + 0.15·freshness + 0.15·health + 0.2·quality
 *
 * Each component lives in 0..1 so the composite is also 0..1. This
 * component renders four horizontal bars (one per component) plus the
 * composite headline. Designed to be usable in two contexts:
 *
 *   - Compact (default): two-column grid suitable for an AgentCard
 *     side panel or a comparison row.
 *   - Detailed (variant='detailed'): full-width bars with labels and
 *     captions explaining what each signal means.
 *
 * Both `score` and `components` are accepted as optional because older
 * /discover responses (pre-composite-scoring) won't carry them. The
 * component renders nothing in that case so existing pages can drop it
 * in without conditional guards.
 */

import type { ScoreComponents } from '@/lib/beckn-api';

interface ScoreBreakdownProps {
  score?: number;
  components?: ScoreComponents;
  variant?: 'compact' | 'detailed';
}

const COLOR_BY_LEVEL = (v: number): string => {
  if (v >= 0.7) return 'var(--trust-high)';
  if (v >= 0.4) return 'var(--trust-mid)';
  return 'var(--trust-low)';
};

const BAR_HEIGHT = 6;

interface Row {
  key: keyof ScoreComponents;
  label: string;
  weight: number;
  caption: string;
}

const ROWS: Row[] = [
  { key: 'semantic', label: 'Relevance',  weight: 0.5,  caption: 'Semantic match with your prompt' },
  { key: 'quality',  label: 'User rating', weight: 0.2,  caption: 'Buyer feedback aggregate' },
  { key: 'freshness', label: 'Freshness', weight: 0.15, caption: 'How recently the agent was published' },
  { key: 'health',    label: 'Uptime',    weight: 0.15, caption: 'Registry health signal' },
];

export function ScoreBreakdown({ score, components, variant = 'compact' }: ScoreBreakdownProps) {
  if (score === undefined || !components) return null;

  const compositeColor = COLOR_BY_LEVEL(score);
  const ratingCount = components.ratingCount ?? 0;

  return (
    <div
      style={{
        background: 'var(--bg-surface, #FFFFFF)',
        border: '1px solid var(--border-subtle, rgba(0,124,195,0.08))',
        borderRadius: 10,
        padding: variant === 'detailed' ? '16px 18px' : '12px 14px',
        fontFamily: 'var(--font-plex)',
      }}
    >
      {/* Headline composite score */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: variant === 'detailed' ? 14 : 10,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10,
              letterSpacing: '0.08em',
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              marginBottom: 2,
            }}
          >
            MARKETPLACE SCORE
          </div>
          <div
            style={{
              fontSize: variant === 'detailed' ? 24 : 18,
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              color: compositeColor,
              lineHeight: 1.1,
            }}
          >
            {score.toFixed(2)}
          </div>
        </div>
        {ratingCount > 0 && (
          <div style={{ textAlign: 'right' }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: '0.08em',
                color: 'var(--text-tertiary)',
                fontFamily: 'var(--font-mono)',
                fontWeight: 700,
                marginBottom: 2,
              }}
            >
              RATINGS
            </div>
            <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
              n = {ratingCount}
            </div>
          </div>
        )}
      </div>

      {/* Component bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: variant === 'detailed' ? 10 : 7 }}>
        {ROWS.map((row) => {
          // `quality` is optional in pre-rate-PR data. Hide the row in
          // that case so we don't show a deceptive 0 bar.
          const v = components[row.key];
          if (v === undefined) return null;
          const numeric = Number(v);
          return (
            <ComponentBar
              key={row.key}
              label={row.label}
              value={numeric}
              weight={row.weight}
              caption={variant === 'detailed' ? row.caption : undefined}
            />
          );
        })}
      </div>
    </div>
  );
}

interface ComponentBarProps {
  label: string;
  value: number;
  weight: number;
  caption?: string;
}

function ComponentBar({ label, value, weight, caption }: ComponentBarProps) {
  const color = COLOR_BY_LEVEL(value);
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 3,
        }}
      >
        <span
          style={{
            fontSize: 11,
            color: 'var(--text-secondary)',
            fontWeight: 500,
          }}
        >
          {label}
          <span
            style={{
              marginLeft: 6,
              fontSize: 10,
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)',
              fontWeight: 400,
            }}
          >
            ×{weight.toFixed(2)}
          </span>
        </span>
        <span
          style={{
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            color,
          }}
        >
          {value.toFixed(2)}
        </span>
      </div>
      <div
        style={{
          height: BAR_HEIGHT,
          background: 'var(--bg-elevated, rgba(0,124,195,0.06))',
          borderRadius: BAR_HEIGHT / 2,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: color,
            transition: 'width 0.4s ease-out',
          }}
        />
      </div>
      {caption && (
        <div
          style={{
            fontSize: 10,
            color: 'var(--text-tertiary)',
            marginTop: 3,
            lineHeight: 1.4,
          }}
        >
          {caption}
        </div>
      )}
    </div>
  );
}
