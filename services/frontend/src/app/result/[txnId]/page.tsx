'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { getFlowState, runBecknFlow, BECKN_STEPS } from '@/lib/mock-beckn';
import type { FlowState, BecknStep } from '@/lib/mock-beckn';

interface ResultPageProps {
  params: Promise<{ txnId: string }>;
}

function StepPill({ step, index }: { step: BecknStep; index: number }) {
  const isDone   = step.status === 'done';
  const isActive = step.status === 'active';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flex: 1 }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `2px solid ${isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'rgba(109,40,217,0.2)'}`,
        background: isDone ? 'rgba(22,163,74,0.1)' : isActive ? 'var(--accent-dim)' : '#F5F3FF',
        transition: 'all 0.3s', flexShrink: 0,
      }}>
        {isDone ? (
          <span style={{ fontSize: 12, color: 'var(--trust-high)' }}>✓</span>
        ) : isActive ? (
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.2s ease-in-out infinite' }} />
        ) : (
          <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{index + 1}</span>
        )}
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          fontSize: 10, fontFamily: 'var(--font-mono)',
          color: isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'var(--text-tertiary)',
          fontWeight: isDone || isActive ? 600 : 400,
          transition: 'color 0.3s', whiteSpace: 'nowrap',
        }}>
          {step.label}
        </div>
        {step.timestamp && (
          <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', marginTop: 2 }}>
            {new Date(step.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)',
      fontWeight: 700, textTransform: 'uppercase',
      color: 'var(--text-tertiary)', marginBottom: 10, marginTop: 22,
    }}>
      {children}
    </div>
  );
}

function ResultCard({ agentId, result }: { agentId: string; result: object }) {
  const isSummarizer = agentId.includes('summarizer');
  const isCodeReview = agentId.includes('code-reviewer');
  const isExtractor  = agentId.includes('data-extractor');
  const r = result as Record<string, unknown>;

  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid rgba(109,40,217,0.1)',
      borderTop: '3px solid var(--accent-send)',
      borderRadius: 18, padding: '28px 32px',
      animation: 'fadeInUp 0.4s ease-out both',
      boxShadow: '0 4px 20px rgba(109,40,217,0.06)',
    }}>
      {isSummarizer && <SummarizerResult r={r} />}
      {isCodeReview && <CodeReviewResult r={r} />}
      {isExtractor  && <ExtractorResult r={r} />}
    </div>
  );
}

function SummarizerResult({ r }: { r: Record<string, unknown> }) {
  const provisions = r.keyProvisions as string[] ?? [];
  const risks = r.riskFactors as string[] ?? [];
  return (
    <div>
      <SectionHead>Summary</SectionHead>
      <p style={{ fontSize: 15, color: 'var(--text-primary)', fontFamily: 'var(--font-dm)', lineHeight: 1.75 }}>
        {r.summary as string}
      </p>
      <SectionHead>Key Provisions</SectionHead>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {provisions.map((p, i) => (
          <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 12, flexShrink: 0, marginTop: 3 }}>§</span>
            <span style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.6 }}>{p}</span>
          </li>
        ))}
      </ul>
      <SectionHead>Risk Factors</SectionHead>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {risks.map((risk, i) => {
          const isHigh = risk.startsWith('HIGH');
          const isMed  = risk.startsWith('MEDIUM');
          const color  = isHigh ? '#DC2626' : isMed ? '#D97706' : 'var(--text-secondary)';
          return (
            <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                background: `${color}12`, color, fontFamily: 'var(--font-mono)',
                fontWeight: 700, flexShrink: 0, marginTop: 2, border: `1px solid ${color}28`,
              }}>
                {isHigh ? 'HIGH' : isMed ? 'MED' : 'LOW'}
              </span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.5 }}>
                {risk.replace(/^(HIGH|MEDIUM|LOW):\s*/i, '')}
              </span>
            </li>
          );
        })}
      </ul>
      <div style={{ display: 'flex', gap: 24, marginTop: 24, paddingTop: 20, borderTop: '1px solid rgba(109,40,217,0.08)' }}>
        {[
          { label: 'Words', value: String(r.wordCount ?? '—') },
          { label: 'Confidence', value: `${Math.round(((r.confidence as number) ?? 0) * 100)}%` },
          { label: 'Language', value: String(r.language ?? 'en').toUpperCase() },
        ].map(m => (
          <div key={m.label}>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 3 }}>{m.label}</div>
            <div style={{ fontSize: 14, color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{m.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CodeReviewResult({ r }: { r: Record<string, unknown> }) {
  const issues = r.issues as Array<Record<string, string>> ?? [];
  const recs   = r.recommendations as string[] ?? [];
  const score  = r.score as number ?? 0;
  const SCOLOR: Record<string, string> = { CRITICAL: '#DC2626', HIGH: '#EA580C', MEDIUM: '#D97706', LOW: '#6B7280' };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginBottom: 4 }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', marginBottom: 6 }}>
            Security Score
          </div>
          <div style={{
            fontSize: 52, fontWeight: 800, fontFamily: 'var(--font-syne)', lineHeight: 1,
            color: score >= 80 ? 'var(--trust-high)' : score >= 60 ? 'var(--trust-mid)' : 'var(--trust-low)',
          }}>
            {score}<span style={{ fontSize: 22, color: 'var(--text-tertiary)', marginLeft: 2, fontWeight: 400 }}>/100</span>
          </div>
        </div>
        <div style={{ flex: 1, paddingLeft: 24, borderLeft: '1px solid rgba(109,40,217,0.1)' }}>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.7 }}>
            {r.review as string}
          </p>
        </div>
      </div>
      <SectionHead>Issues Found</SectionHead>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {issues.map((issue, i) => (
          <div key={i} style={{
            padding: '12px 16px', background: '#FAFAFA',
            border: '1px solid rgba(109,40,217,0.08)',
            borderLeft: `3px solid ${SCOLOR[issue.severity] ?? '#6B7280'}`,
            borderRadius: 10, display: 'flex', gap: 12, alignItems: 'flex-start',
          }}>
            <span style={{
              fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.04em',
              color: SCOLOR[issue.severity] ?? '#6B7280',
              background: `${SCOLOR[issue.severity] ?? '#6B7280'}12`,
              border: `1px solid ${SCOLOR[issue.severity] ?? '#6B7280'}28`,
              padding: '2px 7px', borderRadius: 4, flexShrink: 0, marginTop: 1, fontWeight: 700,
            }}>
              {issue.severity}
            </span>
            <div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-dm)', marginBottom: 3 }}>{issue.description}</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>Line {issue.line} · {issue.rule}</div>
              <div style={{ fontSize: 12, color: 'var(--trust-high)', fontFamily: 'var(--font-dm)', marginTop: 5, fontWeight: 500 }}>→ {issue.suggestion}</div>
            </div>
          </div>
        ))}
      </div>
      <SectionHead>Recommendations</SectionHead>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {recs.map((rec, i) => (
          <li key={i} style={{ display: 'flex', gap: 10, fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)' }}>
            <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', flexShrink: 0, fontWeight: 700 }}>→</span>
            {rec}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExtractorResult({ r }: { r: Record<string, unknown> }) {
  const items = r.lineItems as Array<Record<string, unknown>> ?? [];
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 4 }}>
        {[
          { label: 'Vendor', value: r.vendor as string },
          { label: 'GSTIN', value: r.vendorGSTIN as string },
          { label: 'Invoice #', value: r.invoiceNumber as string },
          { label: 'Date', value: r.invoiceDate as string },
          { label: 'Due Date', value: r.dueDate as string },
          { label: 'Terms', value: r.paymentTerms as string },
        ].map(f => (
          <div key={f.label} style={{ padding: '10px 14px', background: '#F5F3FF', borderRadius: 10, border: '1px solid rgba(109,40,217,0.08)' }}>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 3 }}>{f.label}</div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{f.value}</div>
          </div>
        ))}
      </div>
      <SectionHead>Line Items</SectionHead>
      <div style={{ border: '1px solid rgba(109,40,217,0.1)', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#F5F3FF' }}>
              {['Description', 'HSN', 'Qty', 'Unit Price', 'Amount'].map(h => (
                <th key={h} style={{
                  textAlign: h === 'Description' ? 'left' : 'right',
                  padding: '10px 14px', fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: 'var(--text-tertiary)', letterSpacing: '0.08em', fontWeight: 700,
                  borderBottom: '1px solid rgba(109,40,217,0.08)',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} style={{ borderBottom: '1px solid rgba(109,40,217,0.06)' }}>
                <td style={{ padding: '10px 14px', color: 'var(--text-primary)', fontFamily: 'var(--font-dm)' }}>{item.description as string}</td>
                <td style={{ padding: '10px 14px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{item.hsn as string}</td>
                <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{item.qty as number}</td>
                <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>₹{(item.unitPrice as number).toLocaleString('en-IN')}</td>
                <td style={{ padding: '10px 14px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', textAlign: 'right', fontWeight: 600 }}>₹{(item.amount as number).toLocaleString('en-IN')}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ background: '#F5F3FF' }}>
              <td colSpan={4} style={{ padding: '8px 14px', textAlign: 'right', fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-dm)' }}>Subtotal</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontWeight: 600 }}>₹{(r.subtotal as number)?.toLocaleString('en-IN')}</td>
            </tr>
            <tr style={{ background: '#F5F3FF' }}>
              <td colSpan={4} style={{ padding: '4px 14px', textAlign: 'right', fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-dm)' }}>GST ({r.gstRate as string})</td>
              <td style={{ padding: '4px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontWeight: 600 }}>₹{(r.gstAmount as number)?.toLocaleString('en-IN')}</td>
            </tr>
            <tr style={{ borderTop: '2px solid rgba(109,40,217,0.12)', background: '#F5F3FF' }}>
              <td colSpan={4} style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'var(--font-syne)', color: 'var(--text-primary)', fontWeight: 700, fontSize: 14 }}>Total</td>
              <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 700, fontSize: 16 }}>₹{(r.totalAmount as number)?.toLocaleString('en-IN')}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div style={{ marginTop: 18, display: 'flex', gap: 12 }}>
        {[
          { label: 'Confidence', value: `${Math.round(((r.confidence as number) ?? 0) * 100)}%` },
          { label: 'Currency', value: r.currency as string },
        ].map(m => (
          <div key={m.label} style={{ padding: '10px 14px', background: '#F5F3FF', borderRadius: 10, border: '1px solid rgba(109,40,217,0.08)' }}>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 3 }}>{m.label}</div>
            <div style={{ fontSize: 14, color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{m.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ResultPage({ params }: ResultPageProps) {
  const { txnId } = use(params);
  const [flowState, setFlowState] = useState<FlowState | null>(null);

  useEffect(() => {
    const existing = getFlowState(txnId);
    if (existing?.completed) { setFlowState(existing); return; }

    const agentId   = existing?.agentId   ?? 'agent-summarizer-001';
    const agentName = existing?.agentName ?? 'AI Agent';
    const agentIcon = existing?.agentIcon ?? '🤖';

    if (existing) {
      setFlowState(existing);
    } else {
      setFlowState({
        transactionId: txnId, agentId, agentName, agentIcon,
        steps: BECKN_STEPS.map(s => ({ ...s, status: 'pending' as const })),
        completed: false, startedAt: new Date().toISOString(),
      });
    }

    async function resume() {
      for await (const state of runBecknFlow(agentId, agentName, agentIcon, '')) {
        setFlowState({ ...state, transactionId: txnId });
        if (state.completed) break;
      }
    }

    resume();
  }, [txnId]);

  const completedCount = flowState?.steps.filter(s => s.status === 'done').length ?? 0;

  return (
    <div className="hero-gradient" style={{ minHeight: '100vh' }}>

      {/* Header */}
      <header style={{
        borderBottom: '1px solid rgba(109,40,217,0.1)',
        background: 'rgba(240,237,255,0.85)',
        backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
        position: 'sticky', top: 0, zIndex: 30,
      }}>
        <div style={{
          maxWidth: 960, margin: '0 auto', padding: '0 32px',
          height: 58, display: 'flex', alignItems: 'center', gap: 16,
        }}>
          <Link href="/search" style={{
            fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)',
            textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6,
            fontWeight: 500, transition: 'color 0.15s',
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.color = 'var(--accent)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)')}
          >
            ← New search
          </Link>
          <div style={{ width: 1, height: 16, background: 'rgba(109,40,217,0.15)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
            {txnId.slice(0, 8).toUpperCase()}
          </span>
          <div style={{ flex: 1 }} />
          {flowState?.completed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--trust-high)' }} />
              <span style={{ fontSize: 12, color: 'var(--trust-high)', fontFamily: 'var(--font-dm)', fontWeight: 600 }}>Completed</span>
            </div>
          )}
        </div>
      </header>

      <main style={{ maxWidth: 960, margin: '0 auto', padding: '48px 32px 80px' }}>

        {/* Agent identity */}
        {flowState && (
          <div style={{ marginBottom: 36, animation: 'fadeInUp 0.3s ease-out' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{
                width: 52, height: 52, fontSize: 24,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'white', border: '1px solid rgba(109,40,217,0.12)', borderRadius: 14,
                boxShadow: '0 2px 12px rgba(109,40,217,0.08)',
              }}>
                {flowState.agentIcon}
              </div>
              <div>
                <h1 style={{
                  fontFamily: 'var(--font-syne)', fontSize: 28, fontWeight: 800,
                  color: 'var(--text-primary)', lineHeight: 1.1, letterSpacing: '-0.02em',
                }}>
                  {flowState.agentName}
                </h1>
                <p style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                  Started {new Date(flowState.startedAt).toLocaleString('en-IN')}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Flow tracker */}
        <div style={{
          background: 'white', border: '1px solid rgba(109,40,217,0.1)',
          borderRadius: 18, padding: '24px 28px', marginBottom: 32,
          boxShadow: '0 2px 12px rgba(109,40,217,0.06)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
            <span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              BECKN v2.0 TRANSACTION
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
              {completedCount} / {BECKN_STEPS.length}
            </span>
          </div>

          <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', minWidth: 600 }}>
              {(flowState?.steps ?? BECKN_STEPS.map(s => ({ ...s, status: 'pending' as const }))).map(
                (step, i, arr) => (
                  <div key={step.id} style={{ display: 'flex', alignItems: 'center', flex: i < arr.length - 1 ? 1 : 0 }}>
                    <StepPill step={step} index={i} />
                    {i < arr.length - 1 && (
                      <div style={{
                        height: 1.5, width: 20, flexShrink: 0,
                        background: step.status === 'done' ? 'var(--trust-high)' : 'rgba(109,40,217,0.15)',
                        marginBottom: 28, transition: 'background 0.4s',
                      }} />
                    )}
                  </div>
                ),
              )}
            </div>
          </div>

          {flowState && !flowState.completed && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid rgba(109,40,217,0.08)' }}>
              <div style={{ fontFamily: 'var(--font-dm)', fontSize: 13, color: 'var(--accent)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.2s ease-in-out infinite', flexShrink: 0 }} />
                {flowState.steps.find(s => s.status === 'active')?.description ?? 'Initializing…'}
              </div>
            </div>
          )}
        </div>

        {/* Result */}
        {flowState?.completed && flowState.result && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
              <div style={{ height: 1, flex: 1, background: 'rgba(109,40,217,0.1)' }} />
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', fontWeight: 700 }}>
                AGENT OUTPUT
              </span>
              <div style={{ height: 1, flex: 1, background: 'rgba(109,40,217,0.1)' }} />
            </div>
            <ResultCard agentId={flowState.agentId} result={flowState.result} />
          </div>
        )}

        {/* Loading */}
        {flowState && !flowState.completed && (
          <div style={{
            textAlign: 'center', padding: '56px 24px',
            background: 'white', border: '1px solid rgba(109,40,217,0.1)', borderRadius: 18,
          }}>
            <div style={{
              width: 36, height: 36, margin: '0 auto 16px',
              border: '2.5px solid rgba(109,40,217,0.15)',
              borderTopColor: 'var(--accent)', borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <p style={{ fontFamily: 'var(--font-dm)', fontSize: 14, color: 'var(--text-secondary)', fontWeight: 500 }}>
              Agent executing…
            </p>
          </div>
        )}

        {/* CTA */}
        {flowState?.completed && (
          <div style={{ marginTop: 40 }}>
            <Link
              href="/search"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '11px 22px', background: 'white',
                border: '1.5px solid rgba(109,40,217,0.2)', borderRadius: 10,
                color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)',
                fontSize: 14, fontWeight: 500, textDecoration: 'none', transition: 'all 0.2s',
              }}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLElement;
                el.style.borderColor = 'rgba(109,40,217,0.45)';
                el.style.color = 'var(--accent)';
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLElement;
                el.style.borderColor = 'rgba(109,40,217,0.2)';
                el.style.color = 'var(--text-secondary)';
              }}
            >
              ← Run another agent
            </Link>
          </div>
        )}

      </main>
    </div>
  );
}
