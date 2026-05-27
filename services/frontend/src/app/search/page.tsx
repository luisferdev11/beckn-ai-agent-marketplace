'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import { discover } from '@/lib/beckn-api';
import type { DiscoveredAgent } from '@/lib/beckn-api';
import { AgentCard } from './_components/AgentCard';
import { FilterPanel } from './_components/FilterPanel';
import type { FilterState } from './_components/FilterPanel';
import { AgentModal } from './_components/AgentModal';

type Mode = 'browse' | 'planner';

const DEFAULT_FILTERS: FilterState = {
  data_residency: [],
  credentials: [],
  capabilities: [],
  language_support: [],
  price_max: 5000,
};

const EXAMPLE_PROMPTS: Record<Mode, string[]> = {
  browse: [
    'Summarize a legal contract',
    'Review Python code for security',
    'Extract invoice data',
    'Translate a document to Hindi',
  ],
  planner: [
    'Extract data from invoices and summarize',
    'OCR a scanned PDF and translate to Hindi',
    'Code review then security audit',
  ],
};

const PLACEHOLDER_BY_MODE: Record<Mode, string> = {
  browse: 'Describe the task you need an AI agent to perform…',
  planner: 'Describe a workflow that combines multiple agents…',
};

const RESIDENCY_MAP: Record<string, string> = { India: 'IN', US: 'US', EU: 'EU' };

export default function SearchPage() {
  const [mode, setMode] = useState<Mode>('browse');
  const [query, setQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [agents, setAgents] = useState<DiscoveredAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<DiscoveredAgent | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const filtered = useMemo(() => {
    if (!hasSearched || mode !== 'browse') return [];
    return agents.filter(agent => {
      if (filters.data_residency.length) {
        const j = agent.jurisdiction;
        if (!filters.data_residency.some(r => j === RESIDENCY_MAP[r] || j === r)) return false;
      }
      if (filters.capabilities.length) {
        const skillIds = agent.skills.map(s => s.id.toLowerCase());
        if (!filters.capabilities.some(c => skillIds.some(id => id.includes(c.toLowerCase())))) return false;
      }
      if (filters.language_support.length) {
        const langs = agent.skills.flatMap(s => s.supportedLanguages ?? []);
        if (!filters.language_support.some(l => langs.includes(l))) return false;
      }
      if (agent.pricing.value > filters.price_max) return false;
      return true;
    });
  }, [filters, hasSearched, agents, mode]);

  async function handleSearch() {
    if (!query.trim()) return;
    setHasSearched(true);
    if (mode === 'planner') return;
    setLoading(true);
    setError(null);
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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  }

  function handleReset() {
    setQuery('');
    setHasSearched(false);
    setAgents([]);
    setError(null);
    setFilters(DEFAULT_FILTERS);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleModeChange(next: Mode) {
    if (next === mode) return;
    setMode(next);
    setHasSearched(false);
    setAgents([]);
    setError(null);
  }

  useEffect(() => {
    if (hasSearched && !loading && resultsRef.current) {
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, [hasSearched, loading]);

  return (
    <div style={{ background: 'var(--bg-hero)', minHeight: '100vh' }}>

      {/* ── Hero (dark navy) ── */}
      <section
        className="hero-gradient"
        style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}
      >
        {/* Top bar */}
        <header style={{
          position: 'relative', zIndex: 10,
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
                <span style={{ color: '#007CC3' }}>Infosys</span>
                <span style={{ color: 'rgba(255,255,255,0.35)', margin: '0 10px', fontWeight: 300 }}>|</span>
                <span style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.85)', letterSpacing: '0' }}>
                  AI Agent Marketplace
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%', background: '#00C572',
                  animation: 'pulse 2.5s ease-in-out infinite',
                }} />
                <span style={{ fontSize: 12, color: 'var(--text-on-dark-3)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
                  BECKN v2.0 · TESTNET
                </span>
              </div>
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
            <div style={{
              width: 6, height: 6, borderRadius: '50%', background: '#007CC3',
              flexShrink: 0,
            }} />
            <span style={{ fontSize: 12, fontWeight: 500, color: '#7CC8F0', fontFamily: 'var(--font-plex)', letterSpacing: '0.04em' }}>
              Enterprise AI Platform · Powered by Beckn Protocol
            </span>
          </div>

          {/* Heading */}
          <h1 style={{
            fontFamily: 'var(--font-plex)',
            fontSize: 'clamp(28px, 3.8vw, 46px)',
            fontWeight: 600,
            color: '#FFFFFF',
            lineHeight: 1.15,
            letterSpacing: '-0.02em',
            marginBottom: 14,
            maxWidth: 640,
            animation: 'fadeInUp 0.4s ease-out 0.07s both',
          }}>
            Find the right AI agent<br />
            <span style={{ color: '#7CC8F0', fontWeight: 300 }}>for your business task</span>
          </h1>

          {/* Subtitle */}
          <p style={{
            fontSize: 15,
            color: 'var(--text-on-dark-2)',
            fontFamily: 'var(--font-plex)',
            marginBottom: 28,
            maxWidth: 440,
            lineHeight: 1.65,
            fontWeight: 400,
            animation: 'fadeInUp 0.4s ease-out 0.13s both',
          }}>
            Discover, evaluate, and deploy verified AI agents on the open Beckn network. Ed25519 signed and DeDi verified.
          </p>

          {/* Mode toggle */}
          <ModeToggle mode={mode} onChange={handleModeChange} />

          {/* Search box */}
          <div
            style={{
              width: '100%', maxWidth: 680,
              background: 'rgba(255,255,255,0.97)',
              border: '1px solid rgba(255,255,255,0.25)',
              borderRadius: 8,
              padding: '18px 18px 14px',
              boxShadow: '0 8px 40px rgba(0,0,0,0.3), 0 0 0 1px rgba(0,124,195,0.15)',
              animation: 'fadeInUp 0.4s ease-out 0.20s both',
            }}
          >
            <textarea
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={PLACEHOLDER_BY_MODE[mode]}
              rows={2}
              style={{
                width: '100%',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-plex)', fontSize: 15,
                lineHeight: 1.6, resize: 'none',
                outline: 'none',
                caretColor: 'var(--accent)',
              }}
            />

            {/* Bottom row */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginTop: 12, paddingTop: 12,
              borderTop: '1px solid var(--border-subtle)',
            }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1 }}>
                {EXAMPLE_PROMPTS[mode].map(prompt => (
                  <button
                    key={prompt}
                    onClick={() => setQuery(prompt)}
                    style={{
                      padding: '4px 10px', borderRadius: 4,
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-subtle)',
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-plex)', fontSize: 12, fontWeight: 400,
                      cursor: 'pointer', transition: 'all 0.15s', whiteSpace: 'nowrap',
                    }}
                    onMouseEnter={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.color = 'var(--accent)';
                      el.style.borderColor = 'rgba(0,124,195,0.3)';
                      el.style.background = 'var(--infosys-cobalt-light)';
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.color = 'var(--text-secondary)';
                      el.style.borderColor = 'var(--border-subtle)';
                      el.style.background = 'var(--bg-elevated)';
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
                onMouseEnter={e => {
                  if (query.trim() && !loading) (e.currentTarget as HTMLElement).style.background = 'var(--infosys-cobalt-dark)';
                }}
                onMouseLeave={e => {
                  if (query.trim() && !loading) (e.currentTarget as HTMLElement).style.background = 'var(--infosys-cobalt)';
                }}
              >
                {loading ? 'Searching…' : mode === 'planner' ? 'Plan workflow' : 'Search Agents'}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M7 12V2M7 2L2 7M7 2L12 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
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
              { value: 'Beckn v2.0', label: 'Protocol Version' },
              { value: 'Ed25519', label: 'Signed Transactions' },
              { value: 'DeDi', label: 'Verified Registry' },
              { value: 'CDS', label: 'Catalog Discovery' },
            ].map((stat, i) => (
              <div key={stat.label} style={{
                textAlign: 'center',
                padding: '0 28px',
                borderRight: i < 3 ? '1px solid rgba(255,255,255,0.1)' : 'none',
              }}>
                <div style={{
                  fontSize: 16, fontWeight: 600, color: '#FFFFFF',
                  fontFamily: 'var(--font-plex)',
                }}>
                  {stat.value}
                </div>
                <div style={{
                  fontSize: 11, color: 'var(--text-on-dark-3)',
                  fontFamily: 'var(--font-plex)', marginTop: 3,
                  letterSpacing: '0.03em',
                }}>
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Results (light content area) ── */}
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

            {/* Section header */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 24, paddingBottom: 20,
              borderBottom: '2px solid var(--infosys-cobalt)',
              flexWrap: 'wrap', gap: 12,
            }}>
              <div>
                <h2 style={{
                  fontFamily: 'var(--font-plex)',
                  fontSize: 20, fontWeight: 600,
                  color: 'var(--text-primary)',
                  letterSpacing: '-0.01em',
                }}>
                  {mode === 'planner' ? 'Workflow plan' : 'Available AI Agents'}
                </h2>
                <p style={{
                  fontSize: 13, color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-plex)', marginTop: 3,
                }}>
                  {mode === 'planner'
                    ? 'Planner mode is in preview — wiring coming soon'
                    : loading
                      ? 'Discovering agents…'
                      : `${filtered.length} agent${filtered.length !== 1 ? 's' : ''} · Select one to review details and run`}
                </p>
              </div>

              {mode === 'browse' && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => setFiltersOpen(!filtersOpen)}
                    style={{
                      padding: '7px 14px', borderRadius: 6,
                      background: filtersOpen ? 'var(--infosys-cobalt-light)' : 'var(--bg-surface)',
                      border: `1px solid ${filtersOpen ? 'var(--infosys-cobalt)' : 'var(--border-default)'}`,
                      color: filtersOpen ? 'var(--infosys-cobalt)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', transition: 'all 0.15s',
                      display: 'flex', alignItems: 'center', gap: 6,
                    }}
                  >
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M1 3h12M3 7h8M5 11h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    Refine
                  </button>
                  <button
                    onClick={handleReset}
                    style={{
                      padding: '7px 14px', borderRadius: 6,
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-default)',
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.color = 'var(--infosys-cobalt)';
                      el.style.borderColor = 'var(--infosys-cobalt)';
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget as HTMLElement;
                      el.style.color = 'var(--text-secondary)';
                      el.style.borderColor = 'var(--border-default)';
                    }}
                  >
                    ← New search
                  </button>
                </div>
              )}
            </div>

            {/* Mode-specific content */}
            {mode === 'planner' ? (
              <PlannerPlaceholder query={query} onReset={handleReset} />
            ) : loading ? (
              <LoadingState />
            ) : error ? (
              <ErrorState message={error} onRetry={handleSearch} />
            ) : (
              <>
                {filtersOpen && (
                  <div style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderLeft: '3px solid var(--infosys-cobalt)',
                    borderRadius: 6,
                    padding: '20px 24px',
                    marginBottom: 24,
                    animation: 'slideDown 0.18s ease-out',
                  }}>
                    <FilterPanel filters={filters} onChange={setFilters} complianceMode={false} />
                  </div>
                )}

                {filtered.length > 0 ? (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
                    gap: 18,
                  }}>
                    {filtered.map((agent, i) => (
                      <AgentCard key={agent.id} agent={agent} index={i} onSelect={setSelectedAgent} />
                    ))}
                  </div>
                ) : (
                  <EmptyState onClear={() => setFilters(DEFAULT_FILTERS)} />
                )}
              </>
            )}

            {/* Footer */}
            <div style={{
              marginTop: 48, paddingTop: 20, borderTop: '1px solid var(--border-subtle)',
              display: 'flex', gap: 32, justifyContent: 'center',
            }}>
              {[
                { label: 'Protocol', value: 'Beckn v2.0.0' },
                { label: 'Network',  value: 'beckn.one / testnet' },
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

      {selectedAgent && (
        <AgentModal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />
      )}
    </div>
  );
}

// ── Subcomponents ──────────────────────────────────────────

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center',
      background: 'rgba(255,255,255,0.06)',
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 8, padding: 4, gap: 2,
      marginBottom: 20,
      animation: 'fadeInUp 0.4s ease-out 0.16s both',
    }}>
      <ToggleButton
        active={mode === 'browse'}
        onClick={() => onChange('browse')}
        label="Browse"
        description="Search agents directly"
      />
      <ToggleButton
        active={mode === 'planner'}
        onClick={() => onChange('planner')}
        label="Planner"
        description="Compose multi-agent workflow"
        beta
      />
    </div>
  );
}

function ToggleButton({
  active, onClick, label, description, beta,
}: { active: boolean; onClick: () => void; label: string; description: string; beta?: boolean }) {
  return (
    <button
      onClick={onClick}
      title={description}
      style={{
        padding: '8px 16px', borderRadius: 6, border: 'none',
        background: active ? 'var(--infosys-cobalt)' : 'transparent',
        color: active ? '#fff' : 'rgba(255,255,255,0.72)',
        fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 600,
        cursor: 'pointer', transition: 'all 0.15s',
        display: 'flex', alignItems: 'center', gap: 8,
        boxShadow: active ? '0 2px 10px rgba(0,124,195,0.35)' : 'none',
      }}
      onMouseEnter={e => {
        if (!active) (e.currentTarget as HTMLElement).style.color = '#fff';
      }}
      onMouseLeave={e => {
        if (!active) (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.72)';
      }}
    >
      {label}
      {beta && (
        <span style={{
          fontSize: 9, padding: '1px 6px',
          background: active ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.12)',
          borderRadius: 10, letterSpacing: '0.06em',
          fontWeight: 700,
        }}>
          BETA
        </span>
      )}
    </button>
  );
}

function LoadingState() {
  return (
    <div style={{
      textAlign: 'center', padding: '64px 24px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 6,
    }}>
      <div style={{
        display: 'inline-block', width: 28, height: 28,
        border: '2px solid var(--infosys-cobalt-light)',
        borderTopColor: 'var(--infosys-cobalt)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
        marginBottom: 16,
      }} />
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>
        Discovering agents on the Beckn network…
      </p>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div style={{
      textAlign: 'center', padding: '48px 24px',
      background: 'var(--bg-surface)',
      border: '1px solid rgba(220,38,38,0.2)',
      borderLeft: '3px solid #DC2626',
      borderRadius: 6,
    }}>
      <div style={{ fontSize: 24, color: '#DC2626', marginBottom: 12 }}>⚠</div>
      <p style={{ fontSize: 14, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)', marginBottom: 8, fontWeight: 500 }}>
        Discover failed
      </p>
      <p style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', marginBottom: 20 }}>
        {message}
      </p>
      <button
        onClick={onRetry}
        style={{
          fontSize: 13, padding: '8px 20px',
          background: 'var(--infosys-cobalt)', color: '#fff', border: 'none',
          borderRadius: 6, cursor: 'pointer',
          fontFamily: 'var(--font-plex)', fontWeight: 600,
        }}
      >
        Retry
      </button>
    </div>
  );
}

function EmptyState({ onClear }: { onClear: () => void }) {
  return (
    <div style={{
      textAlign: 'center', padding: '64px 24px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 6,
    }}>
      <div style={{ fontSize: 32, marginBottom: 12, color: 'var(--text-tertiary)' }}>∅</div>
      <p style={{ fontSize: 15, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', marginBottom: 20 }}>
        No agents match the selected filters
      </p>
      <button
        onClick={onClear}
        style={{
          fontSize: 13, color: 'var(--infosys-cobalt)', fontFamily: 'var(--font-plex)', fontWeight: 500,
          background: 'var(--infosys-cobalt-light)', border: '1px solid rgba(0,124,195,0.3)',
          borderRadius: 6, padding: '8px 20px', cursor: 'pointer',
        }}
      >
        Clear filters
      </button>
    </div>
  );
}

function PlannerPlaceholder({ query, onReset }: { query: string; onReset: () => void }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderLeft: '3px solid var(--infosys-cobalt)',
      borderRadius: 8,
      padding: '32px 28px',
    }}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        padding: '4px 10px', borderRadius: 4,
        background: 'var(--infosys-cobalt-light)',
        border: '1px solid rgba(0,124,195,0.25)',
        marginBottom: 16,
      }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--infosys-cobalt)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)' }}>
          PLANNER · PREVIEW
        </span>
      </div>

      <h3 style={{
        fontFamily: 'var(--font-plex)', fontSize: 18, fontWeight: 600,
        color: 'var(--text-primary)', marginBottom: 12, letterSpacing: '-0.01em',
      }}>
        Workflow planning is coming soon
      </h3>

      <p style={{
        fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)',
        lineHeight: 1.6, marginBottom: 20, maxWidth: 620,
      }}>
        In Planner mode you&apos;ll describe a workflow in natural language, and the system
        will decompose it into a sequence of agents — recommending one per step and showing
        alternatives. Wiring to the orchestrator is in progress.
      </p>

      <div style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 6,
        padding: '14px 16px',
        marginBottom: 24,
        fontFamily: 'var(--font-mono)',
        fontSize: 13, color: 'var(--text-secondary)',
      }}>
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: '0.08em', marginBottom: 6 }}>
          YOUR PROMPT
        </div>
        <div style={{ color: 'var(--text-primary)' }}>{query}</div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          onClick={onReset}
          style={{
            padding: '8px 18px', borderRadius: 6,
            background: 'var(--infosys-cobalt)', color: '#fff', border: 'none',
            fontFamily: 'var(--font-plex)', fontSize: 13, fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ← Try browse mode
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)' }}>
          or switch the toggle above
        </span>
      </div>
    </div>
  );
}
