'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import { MOCK_AGENTS } from '@/lib/mock-data';
import type { Agent } from '@/lib/mock-data';
import { AgentCard } from './_components/AgentCard';
import { FilterPanel } from './_components/FilterPanel';
import type { FilterState } from './_components/FilterPanel';
import { AgentModal } from './_components/AgentModal';

const DEFAULT_FILTERS: FilterState = {
  data_residency: [],
  credentials: [],
  capabilities: [],
  language_support: [],
  price_max: 5000,
};

const EXAMPLE_PROMPTS = [
  'Summarize a legal contract',
  'Review Python code for security',
  'Extract invoice data',
  'Translate a document to Hindi',
];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Always show ALL mock agents — text query only triggers the section
  const filtered = useMemo(() => {
    if (!hasSearched) return [];
    return MOCK_AGENTS.filter(agent => {
      if (filters.data_residency.length && !filters.data_residency.some(r => agent.data_residency.includes(r)))
        return false;
      if (filters.credentials.length && !filters.credentials.every(c => agent.credentials.includes(c)))
        return false;
      if (filters.capabilities.length && !filters.capabilities.some(c =>
        agent.capabilities.some(ac => ac.toLowerCase().includes(c.toLowerCase()))))
        return false;
      if (filters.language_support.length && !filters.language_support.some(l => agent.language_support.includes(l)))
        return false;
      if (agent.price_per_task > filters.price_max)
        return false;
      return true;
    });
  }, [filters, hasSearched]);

  function handleSearch() {
    if (!query.trim()) return;
    setHasSearched(true);
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
    setFilters(DEFAULT_FILTERS);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  useEffect(() => {
    if (hasSearched && resultsRef.current) {
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, [hasSearched]);

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
            {/* Infosys wordmark */}
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
            marginBottom: 36,
            maxWidth: 440,
            lineHeight: 1.65,
            fontWeight: 400,
            animation: 'fadeInUp 0.4s ease-out 0.13s both',
          }}>
            Discover, evaluate, and deploy verified AI agents on the open Beckn network. Ed25519 signed and DeDi verified.
          </p>

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
              placeholder="Describe the task you need an AI agent to perform…"
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
                {EXAMPLE_PROMPTS.map(prompt => (
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
                disabled={!query.trim()}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '9px 18px', borderRadius: 6,
                  background: query.trim() ? 'var(--infosys-cobalt)' : 'var(--bg-elevated)',
                  border: 'none',
                  color: query.trim() ? '#fff' : 'var(--text-tertiary)',
                  fontFamily: 'var(--font-plex)', fontWeight: 600, fontSize: 13,
                  cursor: query.trim() ? 'pointer' : 'not-allowed',
                  flexShrink: 0, marginLeft: 12,
                  transition: 'all 0.2s',
                  boxShadow: query.trim() ? '0 2px 10px rgba(0,124,195,0.35)' : 'none',
                }}
                onMouseEnter={e => {
                  if (query.trim()) (e.currentTarget as HTMLElement).style.background = 'var(--infosys-cobalt-dark)';
                }}
                onMouseLeave={e => {
                  if (query.trim()) (e.currentTarget as HTMLElement).style.background = 'var(--infosys-cobalt)';
                }}
              >
                Search Agents
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
              { value: `${MOCK_AGENTS.length}`, label: 'Available Agents' },
              { value: 'Ed25519', label: 'Signed Transactions' },
              { value: 'DeDi', label: 'Verified Registry' },
              { value: 'Beckn v2.0', label: 'Protocol Version' },
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
                  Available AI Agents
                </h2>
                <p style={{
                  fontSize: 13, color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-plex)', marginTop: 3,
                }}>
                  {filtered.length} agent{filtered.length !== 1 ? 's' : ''} · Select one to review details and run
                </p>
              </div>

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
            </div>

            {/* Filters */}
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

            {/* Agent grid */}
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
                  onClick={() => setFilters(DEFAULT_FILTERS)}
                  style={{
                    fontSize: 13, color: 'var(--infosys-cobalt)', fontFamily: 'var(--font-plex)', fontWeight: 500,
                    background: 'var(--infosys-cobalt-light)', border: '1px solid rgba(0,124,195,0.3)',
                    borderRadius: 6, padding: '8px 20px', cursor: 'pointer',
                  }}
                >
                  Clear filters
                </button>
              </div>
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
