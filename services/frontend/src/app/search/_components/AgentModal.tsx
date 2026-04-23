'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import type { Agent } from '@/lib/mock-data';
import { TrustGauge } from './TrustGauge';
import { runBecknFlow } from '@/lib/mock-beckn';
import type { FlowState } from '@/lib/mock-beckn';

interface AgentModalProps {
  agent: Agent;
  onClose: () => void;
}

type RunState = 'idle' | 'selecting' | 'initializing' | 'confirming' | 'done';

const RUN_STEPS: { id: RunState; label: string }[] = [
  { id: 'selecting',    label: 'Selecting' },
  { id: 'initializing', label: 'Negotiating' },
  { id: 'confirming',   label: 'Confirming' },
];

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
      textTransform: 'uppercase', color: 'var(--text-tertiary)',
      fontFamily: 'var(--font-mono)', marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function Tag({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <span style={{
      fontSize: 11, padding: '4px 10px', borderRadius: 20,
      background: accent ? 'var(--accent-dim)' : '#F5F3FF',
      color: accent ? 'var(--accent)' : 'var(--text-secondary)',
      fontFamily: 'var(--font-dm)',
      border: `1px solid ${accent ? 'rgba(109,40,217,0.22)' : 'rgba(109,40,217,0.08)'}`,
      fontWeight: accent ? 600 : 400,
    }}>
      {children}
    </span>
  );
}

export function AgentModal({ agent, onClose }: AgentModalProps) {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [runState, setRunState] = useState<RunState>('idle');
  const [visible, setVisible] = useState(false);
  const genRef = useRef<AsyncGenerator<FlowState> | null>(null);
  const basePrice = agent.price_per_task;
  const gst = +(basePrice * 0.18).toFixed(2);
  const total = +(basePrice + gst).toFixed(2);
  const slaDisplay = agent.sla_p95_seconds < 60
    ? `${agent.sla_p95_seconds}s`
    : `${Math.round(agent.sla_p95_seconds / 60)}m`;

  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(t);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && handleClose();
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  });

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 280);
  }

  async function handleRun() {
    if (!input.trim() || runState !== 'idle') return;
    setRunState('selecting');
    genRef.current = runBecknFlow(agent.id, agent.name, agent.icon, input);
    const stepSequence: RunState[] = ['selecting', 'selecting', 'initializing', 'initializing', 'confirming', 'confirming', 'done'];
    let stepIdx = 0;

    for await (const state of genRef.current) {
      const nextRunState = stepSequence[Math.min(stepIdx++, stepSequence.length - 1)];
      setRunState(nextRunState);
      if (state.completed) {
        setRunState('done');
        await new Promise(r => setTimeout(r, 400));
        router.push(`/result/${state.transactionId}`);
        return;
      }
    }
  }

  const activeStepIdx = RUN_STEPS.findIndex(s => s.id === runState);
  const isRunning = runState !== 'idle' && runState !== 'done';

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={handleClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 40,
          background: 'rgba(17,15,30,0.25)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          opacity: visible ? 1 : 0,
          transition: 'opacity 0.28s ease',
        }}
      />

      {/* Drawer */}
      <aside
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 50,
          width: '100%', maxWidth: 520,
          background: '#FFFFFF',
          borderLeft: '1px solid rgba(109,40,217,0.12)',
          boxShadow: '-12px 0 50px rgba(109,40,217,0.08)',
          display: 'flex', flexDirection: 'column',
          transform: visible ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
          overflowY: 'auto',
        }}
      >
        {/* Accent top */}
        <div style={{
          height: 3,
          background: 'linear-gradient(90deg, var(--accent-send), #A855F7)',
          flexShrink: 0,
        }} />

        {/* Close */}
        <button
          onClick={handleClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: '#F5F3FF', border: '1px solid rgba(109,40,217,0.12)',
            borderRadius: 8, color: 'var(--text-secondary)',
            width: 32, height: 32,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', fontSize: 14, transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.background = 'var(--accent-dim)';
            el.style.color = 'var(--accent)';
          }}
          onMouseLeave={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.background = '#F5F3FF';
            el.style.color = 'var(--text-secondary)';
          }}
        >
          ✕
        </button>

        <div style={{ padding: '28px 28px 40px', display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Agent header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, paddingRight: 44 }}>
            <div style={{
              width: 60, height: 60, fontSize: 26,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: '#F5F3FF', borderRadius: 16, flexShrink: 0,
              border: '1px solid rgba(109,40,217,0.1)',
            }}>
              {agent.icon}
            </div>
            <div style={{ flex: 1 }}>
              <h2 style={{
                fontFamily: 'var(--font-syne)',
                fontSize: 22, fontWeight: 700,
                color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 4,
                letterSpacing: '-0.02em',
              }}>
                {agent.name}
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.5 }}>
                {agent.tagline}
              </p>
              <p style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                {agent.provider}
              </p>
            </div>
            <TrustGauge score={agent.trust_score} />
          </div>

          {/* Description */}
          <div style={{ paddingTop: 4, borderTop: '1px solid rgba(109,40,217,0.08)' }}>
            <Label>About</Label>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.7 }}>
              {agent.long_desc}
            </p>
          </div>

          {/* Capabilities + Languages */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <Label>Capabilities</Label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {agent.capabilities.map(c => <Tag key={c}>{c}</Tag>)}
              </div>
            </div>
            <div>
              <Label>Languages</Label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {agent.language_support.map(l => <Tag key={l}>{l}</Tag>)}
              </div>
            </div>
          </div>

          {/* Compliance */}
          <div>
            <Label>Compliance</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {agent.credentials.map(c => <Tag key={c} accent>{c}</Tag>)}
              {agent.data_residency.map(r => (
                <Tag key={r}>{r === 'India' ? '🇮🇳' : '🌐'} {r}</Tag>
              ))}
            </div>
          </div>

          {/* Pricing + SLA */}
          <div style={{
            background: '#F5F3FF', border: '1px solid rgba(109,40,217,0.1)',
            borderRadius: 14, padding: '18px 20px', display: 'flex', gap: 20,
          }}>
            <div style={{ flex: 1 }}>
              <Label>Pricing</Label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {[
                  { label: 'Base price', value: `₹${basePrice.toFixed(2)}` },
                  { label: 'GST 18%', value: `₹${gst.toFixed(2)}` },
                ].map(row => (
                  <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)' }}>{row.label}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{row.value}</span>
                  </div>
                ))}
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  paddingTop: 8, marginTop: 2, borderTop: '1px solid rgba(109,40,217,0.1)',
                }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-dm)' }}>Total</span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>₹{total.toFixed(2)}</span>
                </div>
              </div>
            </div>
            <div style={{
              borderLeft: '1px solid rgba(109,40,217,0.1)', paddingLeft: 20,
              display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
            }}>
              <Label>SLA</Label>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--trust-high)', fontFamily: 'var(--font-mono)' }}>
                {slaDisplay}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>p95</div>
            </div>
          </div>

          {/* Task input */}
          <div>
            <Label>{agent.input_label}</Label>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={isRunning}
              placeholder={agent.input_placeholder}
              rows={6}
              style={{
                width: '100%', resize: 'vertical',
                background: '#FAFAFA',
                border: `1.5px solid ${input.trim() ? 'rgba(109,40,217,0.3)' : 'rgba(109,40,217,0.12)'}`,
                borderRadius: 12,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-dm)', fontSize: 13,
                padding: '12px 14px', lineHeight: 1.6,
                outline: 'none', transition: 'border-color 0.2s, box-shadow 0.2s',
                opacity: isRunning ? 0.5 : 1, caretColor: 'var(--accent)',
              }}
              onFocus={e => {
                e.currentTarget.style.borderColor = 'rgba(109,40,217,0.5)';
                e.currentTarget.style.boxShadow = '0 0 0 3px rgba(109,40,217,0.1)';
              }}
              onBlur={e => {
                e.currentTarget.style.borderColor = input.trim() ? 'rgba(109,40,217,0.3)' : 'rgba(109,40,217,0.12)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            />
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 4, textAlign: 'right' }}>
              {input.length} chars
            </div>
          </div>

          {/* Run button */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <button
              onClick={handleRun}
              disabled={!input.trim() || isRunning}
              style={{
                width: '100%', padding: '14px 20px',
                background: !input.trim() || isRunning ? '#F5F3FF' : 'var(--accent-send)',
                border: `1.5px solid ${!input.trim() || isRunning ? 'rgba(109,40,217,0.15)' : 'var(--accent-send)'}`,
                borderRadius: 12,
                color: !input.trim() || isRunning ? 'var(--text-tertiary)' : '#fff',
                fontFamily: 'var(--font-syne)', fontWeight: 700, fontSize: 14,
                cursor: !input.trim() || isRunning ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s', letterSpacing: '0.02em',
                boxShadow: input.trim() && !isRunning ? '0 4px 20px rgba(109,40,217,0.3)' : 'none',
              }}
            >
              {isRunning ? 'Running…' : runState === 'done' ? '✓ Redirecting…' : 'Run Agent →'}
            </button>

            {isRunning && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
                {RUN_STEPS.map((step, i) => {
                  const isDone = activeStepIdx > i;
                  const isActive = activeStepIdx === i;
                  return (
                    <div key={step.id} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'rgba(109,40,217,0.15)',
                          animation: isActive ? 'pulse 1s ease-in-out infinite' : 'none',
                          transition: 'background 0.3s',
                        }} />
                        <span style={{
                          fontSize: 10, fontFamily: 'var(--font-dm)',
                          color: isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'var(--text-tertiary)',
                          textAlign: 'center', whiteSpace: 'nowrap',
                        }}>
                          {isDone ? '✓' : step.label}
                        </span>
                      </div>
                      {i < RUN_STEPS.length - 1 && (
                        <div style={{
                          height: 1, width: 24, flexShrink: 0,
                          background: isDone ? 'var(--trust-high)' : 'rgba(109,40,217,0.1)',
                          marginBottom: 18, transition: 'background 0.3s',
                        }} />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Network note */}
          <div style={{
            borderTop: '1px solid rgba(109,40,217,0.08)', paddingTop: 16,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%', background: '#16A34A',
              animation: 'pulse 2.5s ease-in-out infinite', flexShrink: 0,
            }} />
            <p style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', lineHeight: 1.5 }}>
              Routed via Beckn v2.0 · Ed25519 signed · DeDi verified
            </p>
          </div>

        </div>
      </aside>
    </>
  );
}
