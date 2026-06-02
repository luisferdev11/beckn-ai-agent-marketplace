'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { pollStatus, iconForAgent } from '@/lib/beckn-api';
import type { PerformanceAttributes } from '@/lib/beckn-api';
import { RateModal } from '@/app/_components/RateModal';

interface ResultPageProps {
  params: Promise<{ txnId: string }>;
}

type FlowStep = { id: string; label: string; status: 'pending' | 'active' | 'done'; timestamp?: string };

const STEPS: { id: string; label: string }[] = [
  { id: 'select', label: 'Select' },
  { id: 'init', label: 'Init' },
  { id: 'confirm', label: 'Confirm' },
  { id: 'execute', label: 'Execute' },
  { id: 'status', label: 'Result' },
];

interface AgentInfo {
  id: string;
  name: string;
  icon: string;
  provider: string;
}

export default function ResultPage({ params }: ResultPageProps) {
  const { txnId } = use(params);
  const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null);
  const [steps, setSteps] = useState<FlowStep[]>(
    STEPS.map((s, i) => ({ ...s, status: i < 3 ? 'done' : i === 3 ? 'active' : 'pending', timestamp: i < 3 ? new Date().toISOString() : undefined }))
  );
  const [performance, setPerformance] = useState<PerformanceAttributes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [rateOpen, setRateOpen] = useState(false);
  const [lastRatingScore, setLastRatingScore] = useState<number | null>(null);

  // Load agent info from sessionStorage
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(`beckn_agent_${txnId}`);
      if (stored) setAgentInfo(JSON.parse(stored));
    } catch { /* ignore */ }
  }, [txnId]);

  useEffect(() => {
    let stopped = false;

    const run = async () => {
      const maxAttempts = 60; // ~3 minutes (3s intervals) — pipelines may take longer
      for (let i = 0; i < maxAttempts && !stopped; i++) {
        try {
          // Each call triggers a fresh status request and waits for the on_status callback
          const contract = await pollStatus(txnId);
          const perf = contract.performance?.[0];
          const pa = perf?.performanceAttributes;
          const statusCode = pa?.status || perf?.status?.code;

          if ((statusCode === 'COMPLETED' || statusCode === 'PARTIAL') && pa) {
            setPerformance(pa);
            setSteps(prev => prev.map(s =>
              s.id === 'execute' ? { ...s, status: 'done', timestamp: pa.completedAt } :
              s.id === 'status' ? { ...s, status: 'done', timestamp: new Date().toISOString() } :
              s
            ));
            setCompleted(true);
            return;
          } else if (statusCode === 'FAILED') {
            setError(perf?.status?.shortDesc || String(pa?.result?.text ?? 'Agent execution failed'));
            setSteps(prev => prev.map(s =>
              s.id === 'execute' ? { ...s, status: 'done' } :
              s.id === 'status' ? { ...s, status: 'done' } : s
            ));
            setCompleted(true);
            return;
          }
        } catch {
          // pollStatus threw (timeout or network) — retry
        }

        if (!stopped) await new Promise(r => setTimeout(r, 3000));
      }

      if (!stopped) {
        setError('Timeout waiting for agent result');
        setCompleted(true);
      }
    };

    run();
    return () => { stopped = true; };
  }, [txnId]);

  const icon = agentInfo?.icon || iconForAgent(agentInfo?.name || '');
  const agentName = agentInfo?.name || 'AI Agent';

  return (
    <div className="hero-gradient" style={{ minHeight: '100vh' }}>

      {/* Header */}
      <header style={{
        borderBottom: '1px solid rgba(0,124,195,0.1)',
        background: 'rgba(242,245,248,0.92)',
        backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
        position: 'sticky', top: 0, zIndex: 30,
      }}>
        <div style={{
          maxWidth: 960, margin: '0 auto', padding: '0 32px',
          height: 58, display: 'flex', alignItems: 'center', gap: 16,
        }}>
          <Link href="/dashboard" style={{
            fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
            textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6,
            fontWeight: 500,
          }}>
            ← New search
          </Link>
          <div style={{ width: 1, height: 16, background: 'rgba(0,124,195,0.15)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
            {txnId.slice(0, 8).toUpperCase()}
          </span>
          <div style={{ flex: 1 }} />
          {completed && !error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--trust-high)' }} />
              <span style={{ fontSize: 12, color: 'var(--trust-high)', fontFamily: 'var(--font-plex)', fontWeight: 600 }}>Completed</span>
            </div>
          )}
          {completed && error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--trust-low)' }} />
              <span style={{ fontSize: 12, color: 'var(--trust-low)', fontFamily: 'var(--font-plex)', fontWeight: 600 }}>Error</span>
            </div>
          )}
        </div>
      </header>

      <main style={{ maxWidth: 960, margin: '0 auto', padding: '48px 32px 80px' }}>

        {/* Agent identity */}
        <div style={{ marginBottom: 36, animation: 'fadeInUp 0.3s ease-out' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 52, height: 52, fontSize: 24,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'white', border: '1px solid rgba(0,124,195,0.12)', borderRadius: 14,
              boxShadow: '0 2px 12px rgba(0,124,195,0.08)',
            }}>
              {icon}
            </div>
            <div>
              <h1 style={{
                fontFamily: 'var(--font-plex)', fontSize: 28, fontWeight: 800,
                color: 'var(--text-primary)', lineHeight: 1.1, letterSpacing: '-0.02em',
              }}>
                {agentName}
              </h1>
              {agentInfo?.provider && (
                <p style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                  {agentInfo.provider}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Flow tracker */}
        <div style={{
          background: 'white', border: '1px solid rgba(0,124,195,0.1)',
          borderRadius: 18, padding: '24px 28px', marginBottom: 32,
          boxShadow: '0 2px 12px rgba(0,124,195,0.06)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
            <span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              BECKN v2.0 TRANSACTION
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
              {steps.filter(s => s.status === 'done').length} / {steps.length}
            </span>
          </div>

          <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', minWidth: 500 }}>
              {steps.map((step, i) => (
                <div key={step.id} style={{ display: 'flex', alignItems: 'center', flex: i < steps.length - 1 ? 1 : 0 }}>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: `2px solid ${step.status === 'done' ? 'var(--trust-high)' : step.status === 'active' ? 'var(--accent)' : 'rgba(0,124,195,0.2)'}`,
                      background: step.status === 'done' ? 'rgba(0,135,90,0.1)' : step.status === 'active' ? 'var(--accent-dim)' : 'var(--infosys-cobalt-light)',
                      transition: 'all 0.3s',
                    }}>
                      {step.status === 'done' ? (
                        <span style={{ fontSize: 12, color: 'var(--trust-high)' }}>✓</span>
                      ) : step.status === 'active' ? (
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.2s ease-in-out infinite' }} />
                      ) : (
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{i + 1}</span>
                      )}
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{
                        fontSize: 10, fontFamily: 'var(--font-mono)',
                        color: step.status === 'done' ? 'var(--trust-high)' : step.status === 'active' ? 'var(--accent)' : 'var(--text-tertiary)',
                        fontWeight: step.status !== 'pending' ? 600 : 400,
                        whiteSpace: 'nowrap',
                      }}>
                        {step.label}
                      </div>
                    </div>
                  </div>
                  {i < steps.length - 1 && (
                    <div style={{
                      height: 1.5, width: 20, flexShrink: 0,
                      background: step.status === 'done' ? 'var(--trust-high)' : 'rgba(0,124,195,0.15)',
                      marginBottom: 28, transition: 'background 0.4s',
                    }} />
                  )}
                </div>
              ))}
            </div>
          </div>

          {!completed && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid rgba(0,124,195,0.08)' }}>
              <div style={{
                fontFamily: 'var(--font-plex)', fontSize: 13, color: 'var(--accent)', fontWeight: 500,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.2s ease-in-out infinite', flexShrink: 0 }} />
                Agent executing — polling for on_status…
              </div>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: 'white', border: '1px solid rgba(198,40,40,0.15)',
            borderTop: '3px solid var(--trust-low)',
            borderRadius: 18, padding: '28px 32px', marginBottom: 32,
            animation: 'fadeInUp 0.4s ease-out both',
          }}>
            <div style={{ fontSize: 11, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', color: 'var(--trust-low)', fontWeight: 700, marginBottom: 10 }}>
              EXECUTION ERROR
            </div>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', lineHeight: 1.7 }}>
              {error}
            </p>
          </div>
        )}

        {/* Result */}
        {completed && performance && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
              <div style={{ height: 1, flex: 1, background: 'rgba(0,124,195,0.1)' }} />
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', fontWeight: 700 }}>
                AGENT OUTPUT
              </span>
              <div style={{ height: 1, flex: 1, background: 'rgba(0,124,195,0.1)' }} />
            </div>

            <div style={{
              background: '#FFFFFF',
              border: '1px solid rgba(0,124,195,0.1)',
              borderTop: '3px solid var(--infosys-cobalt)',
              borderRadius: 18, padding: '28px 32px',
              animation: 'fadeInUp 0.4s ease-out both',
              boxShadow: '0 4px 20px rgba(0,124,195,0.06)',
            }}>
              {/* Execution metadata */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 20 }}>
                {[
                  { label: 'Status', value: performance.status, color: performance.status === 'COMPLETED' ? 'var(--trust-high)' : 'var(--trust-low)' },
                  { label: 'Model', value: performance.model },
                  { label: 'Latency', value: `${performance.latencyMs}ms` },
                  { label: 'Tokens', value: `${performance.tokensUsed.total} (${performance.tokensUsed.input}in / ${performance.tokensUsed.output}out)` },
                ].map(m => (
                  <div key={m.label} style={{
                    padding: '8px 14px', background: 'var(--infosys-cobalt-light)',
                    borderRadius: 10, border: '1px solid rgba(0,124,195,0.08)',
                  }}>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 3 }}>
                      {m.label}
                    </div>
                    <div style={{
                      fontSize: 13, fontFamily: 'var(--font-mono)', fontWeight: 600,
                      color: 'color' in m ? m.color : 'var(--text-primary)',
                    }}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Pipeline execution summary */}
              {performance.pipeline_mode && performance.execution_summary && (
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontSize: 11, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 10 }}>
                    PIPELINE STEPS
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(performance.execution_summary as { step_id: string; agent: string; status: string; attempts: number; note?: string }[]).map((step) => (
                      <div key={step.step_id} style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '10px 14px', background: 'var(--infosys-cobalt-light)',
                        borderRadius: 10, border: '1px solid rgba(0,124,195,0.08)',
                      }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                          background: step.status === 'success' ? 'var(--trust-high)'
                            : step.status === 'failed' ? 'var(--trust-low)'
                            : step.status === 'skipped' ? 'var(--text-tertiary)'
                            : 'var(--accent)',
                        }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, fontFamily: 'var(--font-plex)', fontWeight: 600, color: 'var(--text-primary)' }}>
                            {step.step_id}: {step.agent}
                          </div>
                          {step.note && (
                            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', marginTop: 2 }}>
                              {step.note}
                            </div>
                          )}
                        </div>
                        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {step.status} ({step.attempts} attempt{step.attempts !== 1 ? 's' : ''})
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Result content */}
              <div style={{ fontSize: 11, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 10 }}>
                {performance.pipeline_mode ? 'PIPELINE OUTPUT' : 'RESULT'}
              </div>

              {performance.result?.text ? (
                <div style={{
                  background: '#FAFCFE', border: '1px solid rgba(0,124,195,0.08)',
                  borderRadius: 12, padding: '18px 20px',
                  fontSize: 14, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)',
                  lineHeight: 1.8, whiteSpace: 'pre-wrap',
                  maxHeight: 500, overflowY: 'auto',
                }}>
                  {performance.result.text as string}
                </div>
              ) : (
                <pre style={{
                  background: '#FAFCFE', border: '1px solid rgba(0,124,195,0.08)',
                  borderRadius: 12, padding: '18px 20px',
                  fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
                  lineHeight: 1.6, whiteSpace: 'pre-wrap', overflow: 'auto',
                  maxHeight: 500,
                }}>
                  {JSON.stringify(performance.result, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}

        {/* Loading spinner */}
        {!completed && (
          <div style={{
            textAlign: 'center', padding: '56px 24px',
            background: 'white', border: '1px solid rgba(0,124,195,0.1)', borderRadius: 18,
          }}>
            <div style={{
              width: 36, height: 36, margin: '0 auto 16px',
              border: '2.5px solid rgba(0,124,195,0.15)',
              borderTopColor: 'var(--accent)', borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <p style={{ fontFamily: 'var(--font-plex)', fontSize: 14, color: 'var(--text-secondary)', fontWeight: 500 }}>
              Agent executing…
            </p>
          </div>
        )}

        {/* Rate CTA — only visible after a successful execution */}
        {completed && !error && performance && (
          <div
            style={{
              marginTop: 28,
              background: 'white',
              border: '1px solid rgba(0,124,195,0.1)',
              borderTop: '3px solid #F5B400',
              borderRadius: 18,
              padding: '24px 28px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
              flexWrap: 'wrap',
              boxShadow: '0 2px 12px rgba(0,124,195,0.06)',
              animation: 'fadeInUp 0.4s ease-out both',
            }}
          >
            <div style={{ flex: '1 1 280px', minWidth: 0 }}>
              <div style={{
                fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
                color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 6,
              }}>
                {lastRatingScore !== null ? 'YOUR RATING' : 'POST-FULFILLMENT'}
              </div>
              <h3 style={{
                fontSize: 16, fontWeight: 600,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-plex)',
                marginBottom: 4,
              }}>
                {lastRatingScore !== null
                  ? `You rated this agent ${lastRatingScore}.0 / 5`
                  : 'Rate this agent'}
              </h3>
              <p style={{
                fontSize: 13,
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-plex)',
                lineHeight: 1.55,
              }}>
                {lastRatingScore !== null
                  ? 'Your rating flows into the marketplace trust score and improves discover rankings for everyone.'
                  : 'Your rating feeds into the agent’s composite trust score — it influences how high it ranks in future discover queries.'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setRateOpen(true)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '11px 22px',
                background: '#F5B400',
                color: '#1A1A1A',
                border: 'none',
                borderRadius: 10,
                fontFamily: 'var(--font-plex)',
                fontSize: 14, fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 2px 10px rgba(245,180,0,0.3)',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 16 }}>★</span>
              {lastRatingScore !== null ? 'Update rating' : 'Rate this agent'}
            </button>
          </div>
        )}

        {/* Back CTA */}
        {completed && (
          <div style={{ marginTop: 40 }}>
            <Link
              href="/dashboard"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '11px 22px', background: 'white',
                border: '1.5px solid rgba(0,124,195,0.2)', borderRadius: 10,
                color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
                fontSize: 14, fontWeight: 500, textDecoration: 'none',
              }}
            >
              ← Run another agent
            </Link>
          </div>
        )}
      </main>

      <RateModal
        open={rateOpen}
        txnId={txnId}
        agentName={agentName}
        agentId={agentInfo?.id}
        onClose={() => setRateOpen(false)}
        onSubmitted={(score) => setLastRatingScore(score)}
      />
    </div>
  );
}
