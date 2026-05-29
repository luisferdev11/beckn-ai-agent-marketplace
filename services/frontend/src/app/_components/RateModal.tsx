'use client';

/**
 * RateModal — captures a buyer rating for a completed transaction.
 *
 * Closes the briefing's Story 1 step 7 ("Priya rates the output 4.5/5").
 * The buyer picks a 1..5 star rating, optionally adds free-form
 * feedback, and submits. Re-rating the same transaction overwrites the
 * previous score (BAP upserts on (transaction_id, target_id,
 * target_type)), so we don't need to track "already rated" state — the
 * modal can be reopened after submit if the user wants to change their
 * mind.
 */

import { useState } from 'react';
import { rateContract } from '@/lib/beckn-api';

interface RateModalProps {
  open: boolean;
  txnId: string;
  agentName: string;
  agentId?: string;
  onClose: () => void;
  onSubmitted?: (score: number) => void;
}

export function RateModal({ open, txnId, agentName, agentId, onClose, onSubmitted }: RateModalProps) {
  const [score, setScore] = useState<number>(0);
  const [hover, setHover] = useState<number>(0);
  const [feedback, setFeedback] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  if (!open) return null;

  const displayScore = hover || score;
  const canSubmit = score >= 1 && score <= 5 && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await rateContract(txnId, score, {
        feedback: feedback.trim() || undefined,
        targetId: agentId,
      });
      setSubmitted(true);
      onSubmitted?.(score);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error submitting rating');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0, 12, 28, 0.55)',
        backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24, zIndex: 100,
        animation: 'fadeIn 0.18s ease-out',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'white',
          borderRadius: 18,
          maxWidth: 520, width: '100%',
          boxShadow: '0 20px 60px rgba(0, 12, 28, 0.4)',
          fontFamily: 'var(--font-plex)',
          overflow: 'hidden',
          animation: 'fadeInUp 0.25s ease-out',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '24px 28px 18px',
            borderBottom: '1px solid rgba(0,124,195,0.08)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
            gap: 12,
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
                marginBottom: 4,
              }}
            >
              BECKN /rate
            </div>
            <h2
              style={{
                fontSize: 19, fontWeight: 700,
                color: 'var(--text-primary)',
                letterSpacing: '-0.01em', lineHeight: 1.25,
              }}
            >
              Rate this agent
            </h2>
            <div
              style={{
                fontSize: 13, color: 'var(--text-secondary)',
                marginTop: 4,
              }}
            >
              {agentName}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 22, color: 'var(--text-tertiary)',
              lineHeight: 1, padding: 0,
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '22px 28px 24px' }}>
          {submitted ? (
            <SubmittedState score={score} onClose={onClose} />
          ) : (
            <>
              {/* Stars */}
              <div style={{ marginBottom: 18 }}>
                <div
                  style={{
                    fontSize: 11,
                    letterSpacing: '0.06em',
                    color: 'var(--text-tertiary)',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    marginBottom: 8,
                  }}
                >
                  YOUR SCORE
                </div>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 10 }}
                  onMouseLeave={() => setHover(0)}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setScore(n)}
                      onMouseEnter={() => setHover(n)}
                      disabled={submitting}
                      aria-label={`${n} star${n === 1 ? '' : 's'}`}
                      style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        fontSize: 32, padding: 0, lineHeight: 1,
                        color: n <= displayScore ? '#F5B400' : 'rgba(0,124,195,0.15)',
                        transition: 'color 0.12s, transform 0.12s',
                        transform: n === hover ? 'scale(1.12)' : 'scale(1)',
                      }}
                    >
                      {n <= displayScore ? '★' : '☆'}
                    </button>
                  ))}
                  <div
                    style={{
                      marginLeft: 10,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14, fontWeight: 600,
                      color: 'var(--text-secondary)',
                      minWidth: 40,
                    }}
                  >
                    {displayScore > 0 ? `${displayScore}.0` : '—'}
                  </div>
                </div>
              </div>

              {/* Feedback */}
              <div style={{ marginBottom: 18 }}>
                <label
                  htmlFor="rating-feedback"
                  style={{
                    display: 'block',
                    fontSize: 11,
                    letterSpacing: '0.06em',
                    color: 'var(--text-tertiary)',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    marginBottom: 6,
                  }}
                >
                  FEEDBACK · OPTIONAL
                </label>
                <textarea
                  id="rating-feedback"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  disabled={submitting}
                  rows={3}
                  placeholder="What worked well? What could improve?"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid var(--border-default, rgba(0,124,195,0.18))',
                    borderRadius: 8,
                    fontSize: 13,
                    fontFamily: 'var(--font-plex)',
                    color: 'var(--text-primary)',
                    background: 'var(--bg-surface, white)',
                    resize: 'vertical',
                    outline: 'none',
                  }}
                />
              </div>

              {error && (
                <div
                  style={{
                    fontSize: 12, color: 'var(--trust-low, #C62828)',
                    background: 'rgba(198,40,40,0.08)',
                    border: '1px solid rgba(198,40,40,0.2)',
                    borderRadius: 8, padding: '8px 12px',
                    marginBottom: 14,
                  }}
                >
                  {error}
                </div>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  type="button"
                  onClick={onClose}
                  disabled={submitting}
                  style={{
                    padding: '9px 16px',
                    borderRadius: 8,
                    background: 'transparent',
                    border: '1px solid var(--border-default, rgba(0,124,195,0.2))',
                    color: 'var(--text-secondary)',
                    fontSize: 13, fontWeight: 500,
                    fontFamily: 'var(--font-plex)',
                    cursor: submitting ? 'not-allowed' : 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  style={{
                    padding: '9px 18px',
                    borderRadius: 8,
                    background: canSubmit ? 'var(--infosys-cobalt, #007CC3)' : 'var(--bg-elevated, rgba(0,124,195,0.06))',
                    color: canSubmit ? '#fff' : 'var(--text-tertiary)',
                    border: 'none',
                    fontSize: 13, fontWeight: 600,
                    fontFamily: 'var(--font-plex)',
                    cursor: canSubmit ? 'pointer' : 'not-allowed',
                    minWidth: 110,
                    boxShadow: canSubmit ? '0 2px 8px rgba(0,124,195,0.3)' : 'none',
                  }}
                >
                  {submitting ? 'Submitting…' : 'Submit rating'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SubmittedState({ score, onClose }: { score: number; onClose: () => void }) {
  return (
    <div style={{ textAlign: 'center', padding: '12px 4px' }}>
      <div
        style={{
          fontSize: 36, color: 'var(--trust-high, #00875A)',
          marginBottom: 12,
        }}
      >
        ✓
      </div>
      <div
        style={{
          fontSize: 16, fontWeight: 600,
          color: 'var(--text-primary)',
          marginBottom: 6,
        }}
      >
        Thanks for rating!
      </div>
      <div
        style={{
          fontSize: 13, color: 'var(--text-secondary)',
          marginBottom: 18,
        }}
      >
        Submitted: <strong>{score}.0 / 5</strong>. Your feedback feeds into the agent&apos;s
        trust score and shows up in future search rankings.
      </div>
      <button
        type="button"
        onClick={onClose}
        style={{
          padding: '9px 22px',
          borderRadius: 8,
          background: 'var(--infosys-cobalt, #007CC3)',
          color: '#fff', border: 'none',
          fontSize: 13, fontWeight: 600,
          fontFamily: 'var(--font-plex)',
          cursor: 'pointer',
        }}
      >
        Close
      </button>
    </div>
  );
}
