'use client';

interface ConformanceResult {
  name: string;
  criticality: 'must' | 'should' | string;
  passed: boolean;
  detail?: string;
  latency_ms?: number | null;
}

interface Conformance {
  must_passed?: boolean | null;
  should_passed?: boolean | null;
  passed_tests?: number;
  total_tests?: number;
  finished_at?: string | null;
  results?: ConformanceResult[];
}

/** Renders the per-test conformance verdict for a BPP (Epic B6). */
export function ConformanceReport({ conformance }: { conformance?: Conformance | null }) {
  if (!conformance) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
        No conformance run on record yet.
      </div>
    );
  }

  const results = conformance.results || [];
  const mustOk = conformance.must_passed === true;

  const mark = (r: ConformanceResult) => {
    if (r.passed) return { label: 'PASS', color: 'var(--trust-high)', bg: 'rgba(0,135,90,0.08)' };
    if (r.criticality === 'must') return { label: 'FAIL', color: 'var(--trust-low)', bg: 'rgba(198,40,40,0.06)' };
    return { label: 'WARN', color: '#b26a00', bg: 'rgba(178,106,0,0.08)' };
  };

  return (
    <div>
      {/* Summary line */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
        fontFamily: 'var(--font-plex)', fontSize: 13,
      }}>
        <span style={{
          padding: '3px 10px', borderRadius: 4, fontSize: 11, fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          background: mustOk ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.06)',
          color: mustOk ? 'var(--trust-high)' : 'var(--trust-low)',
        }}>
          {mustOk ? 'MUST PASSED' : 'MUST FAILED'}
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>
          {conformance.passed_tests ?? 0}/{conformance.total_tests ?? 0} tests passed
        </span>
      </div>

      {/* Per-test rows */}
      <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 6, overflow: 'hidden' }}>
        {results.length === 0 && (
          <div style={{ padding: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
            Run finished without per-test detail.
          </div>
        )}
        {results.map((r, i) => {
          const m = mark(r);
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '7px 12px',
              borderTop: i === 0 ? 'none' : '1px solid var(--border-subtle)',
              fontFamily: 'var(--font-plex)', fontSize: 12,
            }}>
              <span style={{
                minWidth: 42, textAlign: 'center', padding: '2px 6px', borderRadius: 4,
                fontSize: 10, fontWeight: 700, fontFamily: 'var(--font-mono)',
                background: m.bg, color: m.color,
              }}>
                {m.label}
              </span>
              <span style={{
                fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase', minWidth: 44,
              }}>
                {r.criticality}
              </span>
              <span style={{ flex: 1, color: 'var(--text-primary)' }}>
                {r.name}
                {!r.passed && r.detail && (
                  <span style={{ display: 'block', fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {r.detail}
                  </span>
                )}
              </span>
              {typeof r.latency_ms === 'number' && (
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                  {r.latency_ms}ms
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
