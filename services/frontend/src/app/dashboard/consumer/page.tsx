'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SessionDropdown } from '../../_components/shared/SessionDropdown';
import { discover } from '@/lib/beckn-api';
import type { DiscoveredAgent } from '@/lib/beckn-api';
import { AgentCard } from '../../search/_components/AgentCard';
import { AgentModal } from '../../search/_components/AgentModal';

interface User { email: string; role: string; company_name?: string }

const EXAMPLE_PROMPTS = [
  'Summarize a legal contract',
  'Review Python code for security',
  'Extract invoice data',
  'Generate text with Groq',
];

export default function ConsumerDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [query, setQuery] = useState('');
  const [agents, setAgents] = useState<DiscoveredAgent[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<DiscoveredAgent | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/login'); return; }
    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(setUser)
      .catch(() => router.push('/login'));
  }, [router]);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const results = await discover(query);
      setAgents(results);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Discovery failed');
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSearch(); }
  }

  function handleReset() {
    setQuery('');
    setHasSearched(false);
    setAgents([]);
    setError(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  useEffect(() => {
    if (hasSearched && !loading && resultsRef.current) {
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, [hasSearched, loading]);

  if (!user) return null;

  return (
    <div style={{ background: 'var(--bg-hero)', minHeight: '100vh' }}>

      {/* Hero (dark navy) */}
      <section
        className="hero-gradient"
        style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}
      >
        {/* Top bar */}
        <header style={{
          position: 'relative', zIndex: 20,
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(0,24,53,0.5)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}>
          <div style={{
            maxWidth: 1200, margin: '0 auto', padding: '0 32px',
            height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 0,
                fontFamily: 'var(--font-plex)', fontWeight: 700,
                fontSize: 20, letterSpacing: '-0.01em', color: '#FFFFFF',
              }}>
                <img src="/infosys-logo.png" alt="Infosys" style={{ height: 22 }} />
                <span style={{ color: 'rgba(255,255,255,0.35)', margin: '0 10px', fontWeight: 300 }}>|</span>
                <span style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.85)', letterSpacing: '0' }}>
                  AI Agent Marketplace
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button onClick={() => setShowUpgrade(true)} style={{
                padding: '6px 12px', borderRadius: 6,
                background: 'rgba(0,124,195,0.2)', border: '1px solid rgba(0,124,195,0.35)',
                color: '#7CC8F0', fontFamily: 'var(--font-plex)',
                fontSize: 12, fontWeight: 500, cursor: 'pointer',
              }}>
                Register Agent
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%', background: '#00C572',
                  animation: 'pulse 2.5s ease-in-out infinite',
                }} />
                <span style={{ fontSize: 12, color: 'var(--text-on-dark-3)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
                  BECKN v2.0 · TESTNET
                </span>
              </div>
              <SessionDropdown email={user.email} role={user.role} companyName={user.company_name} />
            </div>
          </div>
        </header>

        {/* Hero content */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          padding: '0 24px 80px', position: 'relative', zIndex: 10,
          textAlign: 'center',
        }}>
          {/* Eyebrow badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '5px 14px', borderRadius: 4,
            background: 'rgba(0,124,195,0.2)',
            border: '1px solid rgba(0,124,195,0.35)',
            marginBottom: 24,
            animation: 'fadeInUp 0.4s ease-out both',
          }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#007CC3', flexShrink: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 500, color: '#7CC8F0', fontFamily: 'var(--font-plex)', letterSpacing: '0.04em' }}>
              Enterprise AI Platform · Powered by Beckn Protocol
            </span>
          </div>

          {/* Heading */}
          <h1 style={{
            fontFamily: 'var(--font-plex)',
            fontSize: 'clamp(28px, 3.8vw, 46px)',
            fontWeight: 600, color: '#FFFFFF',
            lineHeight: 1.15, letterSpacing: '-0.02em',
            marginBottom: 14, maxWidth: 640,
            animation: 'fadeInUp 0.4s ease-out 0.07s both',
          }}>
            Find the right AI agent<br />
            <span style={{ color: '#7CC8F0', fontWeight: 300 }}>for your business task</span>
          </h1>

          {/* Subtitle */}
          <p style={{
            fontSize: 15, color: 'var(--text-on-dark-2)',
            fontFamily: 'var(--font-plex)',
            marginBottom: 36, maxWidth: 440,
            lineHeight: 1.65, fontWeight: 400,
            animation: 'fadeInUp 0.4s ease-out 0.13s both',
          }}>
            Discover, evaluate, and deploy verified AI agents on the open Beckn network. Ed25519 signed and DeDi verified.
          </p>

          {/* Search box */}
          <div style={{
            width: '100%', maxWidth: 680,
            background: 'rgba(255,255,255,0.97)',
            border: '1px solid rgba(255,255,255,0.25)',
            borderRadius: 8,
            padding: '18px 18px 14px',
            boxShadow: '0 8px 40px rgba(0,0,0,0.3), 0 0 0 1px rgba(0,124,195,0.15)',
            animation: 'fadeInUp 0.4s ease-out 0.20s both',
          }}>
            <textarea
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe the task you need an AI agent to perform..."
              rows={2}
              disabled={loading}
              style={{
                width: '100%', background: 'transparent',
                border: 'none', color: 'var(--text-primary)',
                fontFamily: 'var(--font-plex)', fontSize: 15,
                lineHeight: 1.6, resize: 'none', outline: 'none',
                caretColor: 'var(--accent)',
                opacity: loading ? 0.5 : 1,
              }}
            />
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginTop: 12, paddingTop: 12,
              borderTop: '1px solid var(--border-subtle)',
            }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1 }}>
                {EXAMPLE_PROMPTS.map(prompt => (
                  <button
                    key={prompt}
                    onClick={() => setQuery(prompt)}
                    disabled={loading}
                    style={{
                      padding: '4px 10px', borderRadius: 4,
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-subtle)',
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-plex)', fontSize: 12, fontWeight: 400,
                      cursor: loading ? 'not-allowed' : 'pointer',
                      transition: 'all 0.15s', whiteSpace: 'nowrap',
                    }}
                    onMouseEnter={e => {
                      if (!loading) {
                        e.currentTarget.style.color = 'var(--accent)';
                        e.currentTarget.style.borderColor = 'rgba(0,124,195,0.3)';
                        e.currentTarget.style.background = 'var(--infosys-cobalt-light)';
                      }
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.color = 'var(--text-secondary)';
                      e.currentTarget.style.borderColor = 'var(--border-subtle)';
                      e.currentTarget.style.background = 'var(--bg-elevated)';
                    }}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <button
                onClick={handleSearch}
                disabled={!query.trim() || loading}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '9px 18px', borderRadius: 6,
                  background: query.trim() && !loading ? 'var(--infosys-cobalt)' : 'var(--bg-elevated)',
                  border: 'none',
                  color: query.trim() && !loading ? '#fff' : 'var(--text-tertiary)',
                  fontFamily: 'var(--font-plex)', fontWeight: 600, fontSize: 13,
                  cursor: query.trim() && !loading ? 'pointer' : 'not-allowed',
                  flexShrink: 0, marginLeft: 12,
                  transition: 'all 0.2s',
                  boxShadow: query.trim() && !loading ? '0 2px 10px rgba(0,124,195,0.35)' : 'none',
                }}
              >
                {loading ? (
                  <>
                    <div style={{
                      width: 14, height: 14,
                      border: '2px solid rgba(255,255,255,0.3)',
                      borderTopColor: '#fff', borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite',
                    }} />
                    Discovering...
                  </>
                ) : (
                  <>
                    Search Agents
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M7 12V2M7 2L2 7M7 2L12 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Stats row */}
          <div style={{
            display: 'flex', gap: 0, marginTop: 32,
            borderTop: '1px solid rgba(255,255,255,0.08)',
            paddingTop: 28,
            animation: 'fadeInUp 0.4s ease-out 0.28s both',
          }}>
            {[
              { value: agents.length > 0 ? String(agents.length) : '—', label: 'Available Agents' },
              { value: 'Ed25519', label: 'Signed Transactions' },
              { value: 'DeDi', label: 'Verified Registry' },
              { value: 'Beckn v2.0', label: 'Protocol Version' },
            ].map((stat, i) => (
              <div key={stat.label} style={{
                textAlign: 'center', padding: '0 28px',
                borderRight: i < 3 ? '1px solid rgba(255,255,255,0.1)' : 'none',
              }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: '#FFFFFF', fontFamily: 'var(--font-plex)' }}>
                  {stat.value}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-on-dark-3)', fontFamily: 'var(--font-plex)', marginTop: 3, letterSpacing: '0.03em' }}>
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Results (light content area) */}
      {hasSearched && (
        <section
          ref={resultsRef}
          className="results-section"
          style={{
            background: 'var(--bg-content)',
            minHeight: '80vh',
            padding: '40px 32px 80px',
          }}
        >
          <div style={{ maxWidth: 1160, margin: '0 auto' }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 24, paddingBottom: 20,
              borderBottom: '2px solid var(--infosys-cobalt)',
              flexWrap: 'wrap', gap: 12,
            }}>
              <div>
                <h2 style={{
                  fontFamily: 'var(--font-plex)', fontSize: 20, fontWeight: 600,
                  color: 'var(--text-primary)', letterSpacing: '-0.01em',
                }}>
                  {loading ? 'Discovering Agents...' : 'Available AI Agents'}
                </h2>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginTop: 3 }}>
                  {loading
                    ? 'Querying Beckn network via ONIX...'
                    : `${agents.length} agent${agents.length !== 1 ? 's' : ''} found · Select one to review and run`
                  }
                </p>
              </div>
              <button
                onClick={handleReset}
                style={{
                  padding: '7px 14px', borderRadius: 6,
                  background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
                  fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                ← New search
              </button>
            </div>

            {error && (
              <div style={{
                padding: '14px 18px', borderRadius: 8, marginBottom: 20,
                background: 'rgba(198,40,40,0.06)', border: '1px solid rgba(198,40,40,0.15)',
                color: 'var(--trust-low)', fontSize: 14, fontFamily: 'var(--font-plex)',
              }}>
                {error}
              </div>
            )}

            {loading && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 18 }}>
                {[1, 2, 3].map(i => (
                  <div key={i} className="skeleton" style={{ height: 220, borderRadius: 18, border: '1px solid var(--border-subtle)' }} />
                ))}
              </div>
            )}

            {!loading && agents.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 18 }}>
                {agents.map((agent, i) => (
                  <AgentCard key={agent.id} agent={agent} index={i} onSelect={setSelectedAgent} />
                ))}
              </div>
            )}

            {!loading && agents.length === 0 && !error && (
              <div style={{
                textAlign: 'center', padding: '64px 24px',
                background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 6,
              }}>
                <div style={{ fontSize: 32, marginBottom: 12, color: 'var(--text-tertiary)' }}>&#8709;</div>
                <p style={{ fontSize: 15, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>
                  No agents found for this query
                </p>
              </div>
            )}

            <div style={{
              marginTop: 48, paddingTop: 20, borderTop: '1px solid var(--border-subtle)',
              display: 'flex', gap: 32, justifyContent: 'center',
            }}>
              {[
                { label: 'Protocol', value: 'Beckn v2.0.0' },
                { label: 'Network', value: 'beckn.one / testnet' },
                { label: 'Registry', value: 'DeDi · fabric.nfh.global' },
              ].map(item => (
                <div key={item.label} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', marginBottom: 2 }}>
                    {item.label.toUpperCase()}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {selectedAgent && <AgentModal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />}

      {/* Upgrade modal */}
      {showUpgrade && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
        }} onClick={() => setShowUpgrade(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: 'var(--bg-surface)', borderRadius: 10, padding: 28,
            maxWidth: 400, textAlign: 'center', boxShadow: '0 8px 40px rgba(0,0,0,0.2)',
          }}>
            <div style={{ fontSize: 24, marginBottom: 12 }}>&#x1F680;</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 8 }}>
              Publisher Account Required
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 18 }}>
              To publish agents you need a Publisher account. Would you like to upgrade your plan?
            </p>
            <a href="/upgrade" style={{
              display: 'inline-block', padding: '10px 24px', borderRadius: 6,
              background: 'var(--infosys-cobalt)', color: '#fff',
              fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
              textDecoration: 'none',
            }}>
              Upgrade Plan
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
