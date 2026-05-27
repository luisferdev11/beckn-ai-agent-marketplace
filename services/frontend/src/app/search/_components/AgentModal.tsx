'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { DiscoveredAgent, ContractData } from '@/lib/beckn-api';
import { selectAgent, initTransaction, confirmTransaction, iconForAgent } from '@/lib/beckn-api';
import { ScoreBreakdown } from '@/app/_components/ScoreBreakdown';

interface AgentModalProps {
  agent: DiscoveredAgent;
  onClose: () => void;
}

type Step = 'details' | 'selecting' | 'pricing' | 'buying' | 'payment' | 'prompt' | 'confirming' | 'redirecting';

const FLOW_STEPS: { id: Step; label: string }[] = [
  { id: 'selecting', label: 'Select' },
  { id: 'buying', label: 'Init' },
  { id: 'payment', label: 'Payment' },
  { id: 'confirming', label: 'Confirm' },
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
      background: accent ? 'var(--accent-dim)' : 'var(--infosys-cobalt-light)',
      color: accent ? 'var(--accent)' : 'var(--text-secondary)',
      fontFamily: 'var(--font-plex)',
      border: `1px solid ${accent ? 'rgba(0,124,195,0.22)' : 'rgba(0,124,195,0.08)'}`,
      fontWeight: accent ? 600 : 400,
    }}>
      {children}
    </span>
  );
}

export function AgentModal({ agent, onClose }: AgentModalProps) {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState<Step>('details');
  const [error, setError] = useState<string | null>(null);
  const [txnId, setTxnId] = useState<string | null>(null);
  const [contract, setContract] = useState<ContractData | null>(null);
  const [prompt, setPrompt] = useState('');
  // Mock payment form
  const [cardNumber, setCardNumber] = useState('4111 1111 1111 1111');
  const [cardExpiry, setCardExpiry] = useState('12/28');
  const [cardCvv, setCardCvv] = useState('123');

  const icon = iconForAgent(agent.name);
  const currSym = agent.pricing.currency === 'INR' ? '₹' : agent.pricing.currency === 'USD' ? '$' : agent.pricing.currency;

  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(t);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape' && step === 'details') handleClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  });

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 280);
  }

  // ── Select ──
  async function handleSelect() {
    setStep('selecting');
    setError(null);
    try {
      const result = await selectAgent(agent.id, agent.offerId);
      setTxnId(result.transactionId);
      setContract(result.contract);
      setStep('pricing');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Select failed');
      setStep('details');
    }
  }

  // ── Init (Buy) ──
  async function handleBuy() {
    if (!txnId) return;
    setStep('buying');
    setError(null);
    try {
      const c = await initTransaction(txnId);
      setContract(c);
      setStep('payment');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Init failed');
      setStep('pricing');
    }
  }

  // ── Payment confirmed → prompt ──
  function handlePaymentConfirm() {
    setStep('prompt');
  }

  // ── Confirm with prompt ──
  async function handleConfirm() {
    if (!txnId) return;
    setStep('confirming');
    setError(null);
    try {
      await confirmTransaction(txnId, prompt || undefined);
      // Save agent info for result page
      sessionStorage.setItem(`beckn_agent_${txnId}`, JSON.stringify({
        id: agent.id,
        name: agent.name,
        icon,
        provider: agent.provider,
      }));
      setStep('redirecting');
      setTimeout(() => router.push(`/result/${txnId}`), 400);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirm failed');
      setStep('prompt');
    }
  }

  // ── Pricing from on_select ──
  const consideration = contract?.consideration?.[0];
  const breakup = consideration?.breakup ?? [];
  const totalPrice = consideration?.price;

  // Progress indicator
  const stepOrder: Step[] = ['selecting', 'buying', 'payment', 'confirming'];
  const currentIdx = stepOrder.indexOf(step);
  const isLoading = ['selecting', 'buying', 'confirming', 'redirecting'].includes(step);

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={() => { if (step === 'details') handleClose(); }}
        style={{
          position: 'fixed', inset: 0, zIndex: 40,
          background: 'rgba(0,24,53,0.3)',
          backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)',
          opacity: visible ? 1 : 0,
          transition: 'opacity 0.28s ease',
        }}
      />

      {/* Drawer */}
      <aside style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 50,
        width: '100%', maxWidth: 540,
        background: '#FFFFFF',
        borderLeft: '1px solid rgba(0,124,195,0.12)',
        boxShadow: '-12px 0 50px rgba(0,48,87,0.12)',
        display: 'flex', flexDirection: 'column',
        transform: visible ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
        overflowY: 'auto',
      }}>
        {/* Top accent bar */}
        <div style={{ height: 3, background: 'linear-gradient(90deg, var(--infosys-cobalt), #005A8E)', flexShrink: 0 }} />

        {/* Close */}
        <button onClick={handleClose} style={{
          position: 'absolute', top: 16, right: 16,
          background: 'var(--infosys-cobalt-light)', border: '1px solid rgba(0,124,195,0.12)',
          borderRadius: 8, color: 'var(--text-secondary)',
          width: 32, height: 32,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', fontSize: 14, zIndex: 2,
        }}>
          ✕
        </button>

        <div style={{ padding: '28px 28px 40px', display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Agent header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, paddingRight: 44 }}>
            <div style={{
              width: 60, height: 60, fontSize: 26,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--infosys-cobalt-light)', borderRadius: 16, flexShrink: 0,
              border: '1px solid rgba(0,124,195,0.1)',
            }}>
              {icon}
            </div>
            <div style={{ flex: 1 }}>
              <h2 style={{
                fontFamily: 'var(--font-plex)',
                fontSize: 22, fontWeight: 700,
                color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 4,
                letterSpacing: '-0.02em',
              }}>
                {agent.name}
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', lineHeight: 1.5 }}>
                {agent.description}
              </p>
              <p style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                {agent.provider}
              </p>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{
              padding: '10px 14px', borderRadius: 8,
              background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)',
              color: 'var(--trust-low)', fontSize: 13, fontFamily: 'var(--font-plex)',
            }}>
              {error}
            </div>
          )}

          {/* ── STEP: Details (initial) ── */}
          {step === 'details' && (
            <>
              {/* Marketplace score breakdown — rendered only when CDS
                  surfaces composite scoring (post-Pieza 2 / composite scoring PR). */}
              {agent.score !== undefined && agent.scoreComponents && (
                <ScoreBreakdown
                  score={agent.score}
                  components={agent.scoreComponents}
                  variant="detailed"
                />
              )}

              <div style={{ paddingTop: 4, borderTop: '1px solid rgba(0,124,195,0.08)' }}>
                <Label>About</Label>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', lineHeight: 1.7 }}>
                  {agent.longDesc}
                </p>
              </div>

              {/* Skills */}
              <div>
                <Label>Skills</Label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {agent.skills.map(s => (
                    <div key={s.id} style={{
                      padding: '8px 12px', background: '#FAFCFE',
                      border: '1px solid rgba(0,124,195,0.06)', borderRadius: 8,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
                        {s.id.replace(/_/g, ' ')}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)', marginTop: 2 }}>
                        {s.description}
                      </div>
                      {s.supportedLanguages?.length ? (
                        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                          {s.supportedLanguages.map(l => <Tag key={l}>{l}</Tag>)}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>

              {/* Quick pricing + SLA */}
              <div style={{
                background: 'var(--infosys-cobalt-light)', border: '1px solid rgba(0,124,195,0.1)',
                borderRadius: 14, padding: '18px 20px', display: 'flex', gap: 20,
              }}>
                <div style={{ flex: 1 }}>
                  <Label>Catalog Price</Label>
                  <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                    {currSym}{agent.pricing.value}
                    <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: 4 }}>
                      / {agent.pricing.model.replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>
                <div style={{
                  borderLeft: '1px solid rgba(0,124,195,0.1)', paddingLeft: 20,
                  display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                }}>
                  <Label>SLA</Label>
                  <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--trust-high)', fontFamily: 'var(--font-mono)' }}>
                    {Math.round(agent.sla.maxLatencyMs / 1000)}s
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>max latency</div>
                </div>
              </div>

              {/* Modalities + Jurisdiction */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {agent.modalities.map(m => <Tag key={m} accent>{m}</Tag>)}
                {agent.jurisdiction && (
                  <Tag>{agent.jurisdiction === 'IN' ? '🇮🇳 India' : agent.jurisdiction === 'US' ? '🇺🇸 US' : agent.jurisdiction}</Tag>
                )}
              </div>

              {/* Select CTA */}
              <button onClick={handleSelect} style={{
                width: '100%', padding: '14px 20px',
                background: 'var(--infosys-cobalt)', border: 'none', borderRadius: 12,
                color: '#fff', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 14,
                cursor: 'pointer', transition: 'all 0.2s',
                boxShadow: '0 4px 20px rgba(0,124,195,0.3)',
              }}>
                Select Agent →
              </button>
            </>
          )}

          {/* ── STEP: Selecting (loading) ── */}
          {step === 'selecting' && <LoadingState message="Sending select to Beckn network…" />}

          {/* ── STEP: Pricing (on_select received) ── */}
          {step === 'pricing' && contract && (
            <>
              <div style={{ paddingTop: 4, borderTop: '1px solid rgba(0,124,195,0.08)' }}>
                <Label>Pricing Breakdown (from BPP)</Label>
                <div style={{
                  background: 'var(--infosys-cobalt-light)', border: '1px solid rgba(0,124,195,0.1)',
                  borderRadius: 14, padding: '18px 20px',
                }}>
                  {breakup.map((b, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>{b.title}</span>
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                        {b.price.currency === 'INR' ? '₹' : '$'}{b.price.value}
                      </span>
                    </div>
                  ))}
                  {totalPrice && (
                    <div style={{
                      display: 'flex', justifyContent: 'space-between',
                      paddingTop: 10, marginTop: 6, borderTop: '1px solid rgba(0,124,195,0.1)',
                    }}>
                      <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>Total</span>
                      <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
                        {totalPrice.currency === 'INR' ? '₹' : '$'}{totalPrice.value}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                Transaction: {txnId?.slice(0, 8)}…
              </div>

              <button onClick={handleBuy} style={{
                width: '100%', padding: '14px 20px',
                background: 'var(--infosys-cobalt)', border: 'none', borderRadius: 12,
                color: '#fff', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 14,
                cursor: 'pointer', boxShadow: '0 4px 20px rgba(0,124,195,0.3)',
              }}>
                Proceed to Payment →
              </button>
            </>
          )}

          {/* ── STEP: Buying (loading init) ── */}
          {step === 'buying' && <LoadingState message="Initializing transaction…" />}

          {/* ── STEP: Payment (mock bank page) ── */}
          {step === 'payment' && (
            <>
              <div style={{
                paddingTop: 4, borderTop: '1px solid rgba(0,124,195,0.08)',
              }}>
                <Label>Payment</Label>
                <div style={{
                  background: '#FAFCFE', border: '1px solid rgba(0,124,195,0.1)',
                  borderRadius: 14, padding: '20px',
                }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18,
                    paddingBottom: 14, borderBottom: '1px solid rgba(0,124,195,0.08)',
                  }}>
                    <div style={{
                      width: 40, height: 26, borderRadius: 4,
                      background: 'linear-gradient(135deg, #1a1f71, #2d6db4)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: 9, fontWeight: 700, fontFamily: 'var(--font-mono)',
                    }}>
                      VISA
                    </div>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', fontWeight: 500 }}>
                      Mock Payment Gateway
                    </span>
                    <span style={{
                      marginLeft: 'auto', fontSize: 10, padding: '2px 6px',
                      background: 'rgba(0,135,90,0.08)', color: 'var(--trust-high)',
                      borderRadius: 4, fontFamily: 'var(--font-mono)',
                    }}>
                      SANDBOX
                    </span>
                  </div>

                  {/* Card number */}
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', display: 'block', marginBottom: 4 }}>
                      Card Number
                    </label>
                    <input
                      value={cardNumber}
                      onChange={e => setCardNumber(e.target.value)}
                      style={{
                        width: '100%', padding: '10px 12px', borderRadius: 8,
                        border: '1px solid var(--border-default)', background: '#fff',
                        fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)',
                        outline: 'none',
                      }}
                    />
                  </div>

                  {/* Expiry + CVV */}
                  <div style={{ display: 'flex', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', display: 'block', marginBottom: 4 }}>
                        Expiry
                      </label>
                      <input
                        value={cardExpiry}
                        onChange={e => setCardExpiry(e.target.value)}
                        style={{
                          width: '100%', padding: '10px 12px', borderRadius: 8,
                          border: '1px solid var(--border-default)', background: '#fff',
                          fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)',
                          outline: 'none',
                        }}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', display: 'block', marginBottom: 4 }}>
                        CVV
                      </label>
                      <input
                        value={cardCvv}
                        onChange={e => setCardCvv(e.target.value)}
                        type="password"
                        style={{
                          width: '100%', padding: '10px 12px', borderRadius: 8,
                          border: '1px solid var(--border-default)', background: '#fff',
                          fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)',
                          outline: 'none',
                        }}
                      />
                    </div>
                  </div>

                  {/* Amount */}
                  {totalPrice && (
                    <div style={{
                      marginTop: 16, paddingTop: 14,
                      borderTop: '1px solid rgba(0,124,195,0.08)',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)' }}>
                        Amount to pay
                      </span>
                      <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
                        {totalPrice.currency === 'INR' ? '₹' : '$'}{totalPrice.value}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <button onClick={handlePaymentConfirm} style={{
                width: '100%', padding: '14px 20px',
                background: '#00875A', border: 'none', borderRadius: 12,
                color: '#fff', fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 14,
                cursor: 'pointer', boxShadow: '0 4px 20px rgba(0,135,90,0.3)',
              }}>
                Pay {totalPrice ? `${totalPrice.currency === 'INR' ? '₹' : '$'}${totalPrice.value}` : ''} →
              </button>
            </>
          )}

          {/* ── STEP: Prompt (user writes task) ── */}
          {step === 'prompt' && (
            <>
              <div style={{
                padding: '10px 14px', borderRadius: 8,
                background: 'rgba(0,135,90,0.06)', border: '1px solid rgba(0,135,90,0.15)',
                color: 'var(--trust-high)', fontSize: 12, fontFamily: 'var(--font-plex)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span style={{ fontSize: 16 }}>✓</span>
                Payment confirmed (sandbox)
              </div>

              <div>
                <Label>Your task for {agent.name}</Label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={`Describe what you want ${agent.name} to do…`}
                  rows={6}
                  style={{
                    width: '100%', resize: 'vertical',
                    background: '#FAFCFE',
                    border: `1.5px solid ${prompt.trim() ? 'rgba(0,124,195,0.3)' : 'rgba(0,124,195,0.12)'}`,
                    borderRadius: 12,
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-plex)', fontSize: 13,
                    padding: '12px 14px', lineHeight: 1.6,
                    outline: 'none', transition: 'border-color 0.2s',
                  }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'rgba(0,124,195,0.5)'; }}
                  onBlur={e => { e.currentTarget.style.borderColor = prompt.trim() ? 'rgba(0,124,195,0.3)' : 'rgba(0,124,195,0.12)'; }}
                />
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 4, textAlign: 'right' }}>
                  {prompt.length} chars
                </div>
              </div>

              <button
                onClick={handleConfirm}
                disabled={!prompt.trim()}
                style={{
                  width: '100%', padding: '14px 20px',
                  background: prompt.trim() ? 'var(--infosys-cobalt)' : 'var(--bg-elevated)',
                  border: 'none', borderRadius: 12,
                  color: prompt.trim() ? '#fff' : 'var(--text-tertiary)',
                  fontFamily: 'var(--font-plex)', fontWeight: 700, fontSize: 14,
                  cursor: prompt.trim() ? 'pointer' : 'not-allowed',
                  boxShadow: prompt.trim() ? '0 4px 20px rgba(0,124,195,0.3)' : 'none',
                }}
              >
                Confirm & Run Agent →
              </button>
            </>
          )}

          {/* ── STEP: Confirming / Redirecting ── */}
          {step === 'confirming' && <LoadingState message="Confirming transaction & starting agent…" />}
          {step === 'redirecting' && <LoadingState message="Redirecting to results…" />}

          {/* Progress indicator (visible during flow) */}
          {step !== 'details' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
              {FLOW_STEPS.map((fs, i) => {
                const fsIdx = stepOrder.indexOf(fs.id);
                const isDone = currentIdx > fsIdx || step === 'redirecting';
                const isActive = currentIdx === fsIdx && isLoading;
                return (
                  <div key={fs.id} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'rgba(0,124,195,0.15)',
                        animation: isActive ? 'pulse 1s ease-in-out infinite' : 'none',
                        transition: 'background 0.3s',
                      }} />
                      <span style={{
                        fontSize: 10, fontFamily: 'var(--font-plex)',
                        color: isDone ? 'var(--trust-high)' : isActive ? 'var(--accent)' : 'var(--text-tertiary)',
                        textAlign: 'center', whiteSpace: 'nowrap',
                      }}>
                        {isDone ? '✓' : fs.label}
                      </span>
                    </div>
                    {i < FLOW_STEPS.length - 1 && (
                      <div style={{
                        height: 1, width: 24, flexShrink: 0,
                        background: isDone ? 'var(--trust-high)' : 'rgba(0,124,195,0.1)',
                        marginBottom: 18, transition: 'background 0.3s',
                      }} />
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Network badge */}
          <div style={{
            borderTop: '1px solid rgba(0,124,195,0.08)', paddingTop: 16,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%', background: '#00875A',
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

function LoadingState({ message }: { message: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0' }}>
      <div style={{
        width: 32, height: 32, margin: '0 auto 14px',
        border: '2.5px solid rgba(0,124,195,0.15)',
        borderTopColor: 'var(--accent)', borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <p style={{ fontFamily: 'var(--font-plex)', fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
        {message}
      </p>
    </div>
  );
}
