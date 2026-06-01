'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';
import { discover, plan as planWorkflow } from '@/lib/beckn-api';
import type { DiscoveredAgent, Plan, PlanStep } from '@/lib/beckn-api';
import { AgentCard } from './AgentCard';
import { FilterPanel } from './FilterPanel';
import type { FilterState } from './FilterPanel';
import { AgentModal } from './AgentModal';

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

// ── Mapping helpers ────────────────────────────────────────
//
// The frontend filter UI uses display-friendly country/language names,
// while the CDS stores ISO-3166-alpha-3 jurisdictions and ISO-639-1
// language codes inside AgentFacts. We map at filter time so the
// DiscoveredAgent contract stays unchanged.

// Maps both ISO-3166 alpha-3 (preferred — set in our migrations) and the
// alpha-2 codes some legacy seeds still use, so the filter UI stays usable
// no matter which the BPP declared.
const COUNTRY_BY_JURISDICTION: Record<string, string> = {
  IND: 'India',     IN: 'India',
  USA: 'United States', US: 'United States',
  MEX: 'Mexico',    MX: 'Mexico',
  GBR: 'United Kingdom', GB: 'United Kingdom',
  SGP: 'Singapore', SG: 'Singapore',
  ARE: 'United Arab Emirates', AE: 'United Arab Emirates',
};

const LANGUAGE_BY_CODE: Record<string, string> = {
  en: 'English',
  hi: 'Hindi',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  pt: 'Portuguese',
  ja: 'Japanese',
  ar: 'Arabic',
  ta: 'Tamil',
  zh: 'Chinese',
};

function dataResidencyOf(agent: DiscoveredAgent): string {
  if (!agent.jurisdiction) return 'Unknown';
  return COUNTRY_BY_JURISDICTION[agent.jurisdiction] ?? agent.jurisdiction;
}

function capabilitiesOf(agent: DiscoveredAgent): string[] {
  return agent.skills.map(s => s.id).filter(Boolean);
}

function languagesOf(agent: DiscoveredAgent): string[] {
  const codes = new Set<string>();
  for (const skill of agent.skills) {
    for (const code of skill.supportedLanguages ?? []) codes.add(code);
  }
  return Array.from(codes).map(c => LANGUAGE_BY_CODE[c] ?? c);
}

/**
 * Full agent-discovery experience: Browse/Planner toggle, filters, discover
 * results and the workflow planner. The page-level top bar is injected via
 * `header` so the same discovery surface can sit behind the public `/search`
 * chrome or the authenticated consumer-dashboard chrome without duplicating
 * the search logic (which is exactly how the two drifted apart before).
 */
export function AgentDiscovery({ header }: { header?: ReactNode }) {
  const [mode, setMode] = useState<Mode>('browse');
  const [query, setQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [agents, setAgents] = useState<DiscoveredAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<DiscoveredAgent | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [planResult, setPlanResult] = useState<Plan | null>(null);
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
    setLoading(true);
    setError(null);
    try {
      if (mode === 'planner') {
        const result = await planWorkflow(query);
        setPlanResult(result);
      } else {
        const results = await discover(query);
        setAgents(results);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : mode === 'planner' ? 'Plan failed' : 'Discovery failed';
      setError(message);
      if (mode === 'planner') setPlanResult(null);
      else setAgents([]);
    } finally {
      setLoading(false);
    }
  }

  function handleRunPipeline() {
    // Stub: pipeline execution wiring (select → init → confirm → status per step)
    // lands in a follow-up iteration. For now the planner output is read-only.
    alert('Pipeline execution coming soon — the plan is read-only for this iteration.');
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
    setPlanResult(null);
    setError(null);
    setFilters(DEFAULT_FILTERS);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleModeChange(next: Mode) {
    if (next === mode) return;
    setMode(next);
    setHasSearched(false);
    setAgents([]);
    setPlanResult(null);
    setError(null);
  }

  useEffect(() => {
    // When returning to the search state (New search), scroll back to top.
    if (!hasSearched) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [hasSearched]);

  return (
    <div style={{ background: 'var(--bg-hero)', minHeight: '100vh' }}>

      {/* ── Hero (dark navy) ── */}
      <section
        className="hero-gradient"
        style={{
          minHeight: hasSearched ? 'auto' : '100vh',
          display: 'flex', flexDirection: 'column', position: 'relative',
        }}
      >
        {/* Top bar — injected by the host page (public or authenticated chrome) */}
        {header}

        {/* Hero content — only mounted before search. New-search restores it. */}
        {!hasSearched && (
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
              disabled={loading}
              style={{
                width: '100%',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-plex)', fontSize: 15,
                lineHeight: 1.6, resize: 'none',
                outline: 'none',
                caretColor: 'var(--accent)',
                opacity: loading ? 0.6 : 1,
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
                    disabled={loading}
                    style={{
                      padding: '4px 10px', borderRadius: 4,
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-subtle)',
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-plex)', fontSize: 12, fontWeight: 400,
                      cursor: loading ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
                      whiteSpace: 'nowrap', opacity: loading ? 0.5 : 1,
                    }}
                    onMouseEnter={e => {
                      if (loading) return;
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
        )}
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
                    ? loading
                      ? 'Composing pipeline — extracting skills and matching agents…'
                      : error
                        ? 'Pipeline composition failed'
                        : planResult
                          ? `${planResult.estimates.steps_count} step${planResult.estimates.steps_count !== 1 ? 's' : ''} · ~${planResult.estimates.currency} ${planResult.estimates.total_cost.toFixed(2)} · ~${Math.round(planResult.estimates.max_latency_ms / 1000)}s end-to-end`
                          : 'Describe a workflow that combines multiple agents'
                    : loading
                      ? 'Discovering agents…'
                      : `${filtered.length} agent${filtered.length !== 1 ? 's' : ''} · Select one to review details and run`}
                </p>
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                {mode === 'browse' && (
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
                )}
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
            </div>

            {/* Mode-specific content */}
            {mode === 'planner' ? (
              loading ? (
                <PlanLoadingState />
              ) : error ? (
                <ErrorState message={error} onRetry={handleSearch} />
              ) : planResult ? (
                <PlanResults plan={planResult} onRun={handleRunPipeline} />
              ) : (
                <PlanEmptyState />
              )
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

// ── Planner result components ──────────────────────────────

function PlanResults({ plan, onRun }: { plan: Plan; onRun: () => void }) {
  const totalSeconds = (plan.estimates.max_latency_ms / 1000).toFixed(plan.estimates.max_latency_ms < 10000 ? 1 : 0);
  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out both' }}>
      {/* Plan summary hero */}
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderLeft: '3px solid var(--infosys-cobalt)',
        borderRadius: 8,
        padding: '20px 24px',
        marginBottom: 28,
      }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '3px 10px', borderRadius: 4,
          background: 'var(--infosys-cobalt-light)',
          border: '1px solid rgba(0,124,195,0.25)',
          marginBottom: 12,
        }}>
          <span style={{
            fontSize: 10, fontWeight: 700, color: 'var(--infosys-cobalt)',
            letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
          }}>
            PIPELINE · {plan.steps.length} STEPS
          </span>
        </div>
        <p style={{
          fontSize: 15, color: 'var(--text-primary)', fontFamily: 'var(--font-plex)',
          lineHeight: 1.5, marginBottom: 14, fontWeight: 500,
        }}>
          {plan.summary}
        </p>
        <div style={{
          display: 'flex', gap: 28, flexWrap: 'wrap',
          paddingTop: 12, borderTop: '1px solid var(--border-subtle)',
        }}>
          <PlanStat label="Est. cost" value={`${plan.estimates.currency} ${plan.estimates.total_cost.toFixed(2)}`} />
          <PlanStat label="Worst-case latency" value={`~${totalSeconds}s`} />
          <PlanStat label="Steps" value={String(plan.estimates.steps_count)} />
          <PlanStat label="On error" value={plan.on_error} />
        </div>
      </div>

      {/* Pipeline timeline */}
      <div style={{ position: 'relative' }}>
        {plan.steps.map((step, i) => (
          <PlanStepCard
            key={step.id}
            step={step}
            index={i}
            isLast={i === plan.steps.length - 1}
          />
        ))}
      </div>

      {/* Run pipeline (stub) */}
      <div style={{
        marginTop: 28,
        display: 'flex', justifyContent: 'center',
        animation: `fadeInUp 0.4s ease-out ${0.12 + plan.steps.length * 0.08}s both`,
      }}>
        <button
          onClick={onRun}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '12px 28px', borderRadius: 8,
            background: 'var(--infosys-cobalt)', color: '#fff', border: 'none',
            fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
            cursor: 'pointer', transition: 'all 0.15s',
            boxShadow: '0 4px 16px rgba(0,124,195,0.35)',
          }}
          onMouseEnter={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.background = 'var(--infosys-cobalt-dark)';
            el.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.background = 'var(--infosys-cobalt)';
            el.style.transform = 'translateY(0)';
          }}
        >
          Run pipeline
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 7h10M12 7l-4-4M12 7l-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function PlanStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{
        fontSize: 10, color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
        textTransform: 'uppercase', marginBottom: 3,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 14, color: 'var(--text-primary)',
        fontFamily: 'var(--font-plex)', fontWeight: 600,
      }}>
        {value}
      </div>
    </div>
  );
}

function PlanStepCard({ step, index, isLast }: { step: PlanStep; index: number; isLast: boolean }) {
  const [altOpen, setAltOpen] = useState(false);
  const rec = step.recommended;
  const latencySec = rec.latency_ms >= 1000
    ? `${(rec.latency_ms / 1000).toFixed(rec.latency_ms < 10000 ? 1 : 0)}s`
    : `${rec.latency_ms}ms`;

  return (
    <div style={{
      position: 'relative',
      animation: `fadeInUp 0.4s ease-out ${0.08 + index * 0.08}s both`,
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '40px 1fr',
        gap: 16,
      }}>
        {/* Left rail: step number + connector */}
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%',
            background: 'var(--infosys-cobalt)',
            color: '#fff', fontFamily: 'var(--font-plex)',
            fontSize: 14, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0,124,195,0.4)',
            flexShrink: 0,
          }}>
            {index + 1}
          </div>
          {!isLast && (
            <div style={{
              flex: 1,
              width: 2,
              background: 'linear-gradient(to bottom, var(--infosys-cobalt) 0%, rgba(0,124,195,0.35) 100%)',
              marginTop: 6,
              marginBottom: 6,
              minHeight: 24,
            }} />
          )}
        </div>

        {/* Right: step card */}
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 8,
          padding: '18px 22px',
          marginBottom: isLast ? 0 : 12,
          transition: 'border-color 0.15s, box-shadow 0.15s',
        }}>
          {/* Step header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, flexWrap: 'wrap', marginBottom: 14,
          }}>
            <div>
              <div style={{
                fontFamily: 'var(--font-plex)', fontSize: 15, fontWeight: 600,
                color: 'var(--text-primary)', letterSpacing: '-0.01em',
              }}>
                {step.skill_id}
              </div>
              <div style={{
                fontSize: 11, color: 'var(--text-tertiary)',
                fontFamily: 'var(--font-mono)', marginTop: 2,
              }}>
                {step.id}
                {step.depends_on.length > 0 && (
                  <span> · depends on {step.depends_on.join(', ')}</span>
                )}
              </div>
            </div>
          </div>

          {/* Recommended agent */}
          <div style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderLeft: '3px solid var(--infosys-cobalt)',
            borderRadius: 6,
            padding: '12px 14px',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              marginBottom: 6,
            }}>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: '2px 6px',
                background: 'var(--infosys-cobalt-light)',
                color: 'var(--infosys-cobalt)', borderRadius: 3,
                fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
              }}>
                RECOMMENDED
              </span>
              <span style={{
                fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
                color: 'var(--text-primary)',
              }}>
                {rec.name}
              </span>
              <span style={{
                fontSize: 12, color: 'var(--text-tertiary)',
                fontFamily: 'var(--font-plex)',
              }}>
                · {rec.provider}
              </span>
            </div>
            <div style={{
              display: 'flex', gap: 16, marginBottom: 8,
              fontSize: 12, color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
            }}>
              <span>
                <span style={{ color: 'var(--text-tertiary)' }}>cost</span>{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{rec.currency} {rec.cost.toFixed(2)}</strong>
              </span>
              <span>
                <span style={{ color: 'var(--text-tertiary)' }}>latency</span>{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{latencySec}</strong>
              </span>
            </div>
            <p style={{
              fontSize: 12, color: 'var(--text-secondary)',
              fontFamily: 'var(--font-plex)', lineHeight: 1.5,
              fontStyle: 'italic',
            }}>
              “{rec.reason}”
            </p>
          </div>

          {/* Input mapping (subtle) */}
          {Object.keys(step.input_mapping).length > 0 && (
            <div style={{
              marginTop: 10,
              fontSize: 11, color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)', lineHeight: 1.6,
            }}>
              {Object.entries(step.input_mapping).map(([k, v]) => (
                <div key={k}>
                  <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                  <span style={{ margin: '0 6px' }}>←</span>
                  <span>{v}</span>
                </div>
              ))}
            </div>
          )}

          {/* Alternatives */}
          {step.alternatives.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <button
                onClick={() => setAltOpen(!altOpen)}
                style={{
                  background: 'transparent', border: 'none',
                  color: 'var(--infosys-cobalt)', cursor: 'pointer',
                  fontFamily: 'var(--font-plex)', fontSize: 12, fontWeight: 500,
                  padding: 0,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none"
                     style={{ transform: altOpen ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>
                  <path d="M3 1l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {step.alternatives.length} alternative{step.alternatives.length !== 1 ? 's' : ''}
              </button>
              {altOpen && (
                <div style={{
                  marginTop: 8,
                  borderLeft: '2px solid var(--border-default)',
                  paddingLeft: 12,
                  display: 'flex', flexDirection: 'column', gap: 8,
                }}>
                  {step.alternatives.map(alt => (
                    <div key={alt.agent_id} style={{
                      fontSize: 12, fontFamily: 'var(--font-plex)',
                      color: 'var(--text-secondary)',
                    }}>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                        <strong style={{ color: 'var(--text-primary)' }}>{alt.name}</strong>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                          {rec.currency} {alt.cost.toFixed(2)} · {alt.latency_ms >= 1000 ? `${(alt.latency_ms / 1000).toFixed(1)}s` : `${alt.latency_ms}ms`}
                        </span>
                      </div>
                      {alt.note && (
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                          {alt.note}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PlanLoadingState() {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderLeft: '3px solid var(--infosys-cobalt)',
      borderRadius: 8,
      padding: '48px 28px',
      textAlign: 'center',
    }}>
      <div style={{
        display: 'inline-block', width: 28, height: 28,
        border: '2px solid var(--infosys-cobalt-light)',
        borderTopColor: 'var(--infosys-cobalt)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
        marginBottom: 16,
      }} />
      <p style={{
        fontSize: 14, color: 'var(--text-primary)',
        fontFamily: 'var(--font-plex)', fontWeight: 500,
        marginBottom: 6,
      }}>
        Composing your pipeline
      </p>
      <p style={{
        fontSize: 12, color: 'var(--text-secondary)',
        fontFamily: 'var(--font-plex)',
      }}>
        Extracting skills → discovering agents → assembling the workflow. This takes 5–15s.
      </p>
    </div>
  );
}

function PlanEmptyState() {
  return (
    <div style={{
      textAlign: 'center', padding: '48px 24px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 6,
    }}>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>
        Describe a multi-step workflow to compose a pipeline.
      </p>
    </div>
  );
}
