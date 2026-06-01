'use client';

/**
 * Story 1 cross-BPP demo page.
 *
 * Renders the controlled marketplace pipeline (Tecla legal summarizer
 * → Serg structured extractor) end-to-end:
 *
 *   1. Fetches the demo spec on mount (agents, schemas, sample doc).
 *   2. User edits the sample document (or pastes their own).
 *   3. "Run Pipeline" calls /api/demo/legal-pipeline. The runner
 *      executes the full Beckn flow for each step and validates the
 *      payload against the agent's declared JSON Schema.
 *   4. UI renders: pipeline overview (top), per-step trace cards
 *      (middle), final structured output (bottom).
 */

import { useEffect, useState } from 'react';
import {
  fetchDemoSpec,
  runLegalPipeline,
  type DemoResult,
  type DemoSpec,
  type StepTrace,
} from '@/lib/demo-api';

export default function DemoPage() {
  const [spec, setSpec] = useState<DemoSpec | null>(null);
  const [document, setDocument] = useState('');
  const [language] = useState('en');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DemoResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDemoSpec()
      .then((s) => {
        setSpec(s);
        setDocument(s.sample_document);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'spec load failed'));
  }, []);

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runLegalPipeline(document, language);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'pipeline failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ background: 'var(--bg-content, #F2F5F8)', minHeight: '100vh', paddingBottom: 64 }}>
      <Header />

      <main style={{ maxWidth: 1080, margin: '0 auto', padding: '32px 24px' }}>
        <Intro />

        {spec && <PipelineSpec spec={spec} />}

        <DocumentInput
          value={document}
          onChange={setDocument}
          disabled={loading}
        />

        <RunButton onClick={handleRun} loading={loading} disabled={!document.trim()} />

        {error && <ErrorBanner message={error} />}

        {(loading || result) && (
          <ResultsSection loading={loading} result={result} spec={spec} />
        )}
      </main>
    </div>
  );
}

// ── Pieces ──────────────────────────────────────────────────────────

function Header() {
  return (
    <header style={{
      background: 'var(--bg-hero, #001835)',
      color: '#fff',
      padding: '20px 24px',
      borderBottom: '1px solid rgba(255,255,255,0.08)',
    }}>
      <div style={{ maxWidth: 1080, margin: '0 auto' }}>
        <div style={{
          fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
          color: 'rgba(255,255,255,0.5)', fontWeight: 700, marginBottom: 4,
        }}>
          DEMO · STORY 1 · CROSS-BPP PIPELINE
        </div>
        <h1 style={{
          fontFamily: 'var(--font-plex)',
          fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em',
        }}>
          Regulatory Document Analysis (Tecla → Serg)
        </h1>
      </div>
    </header>
  );
}

function Intro() {
  return (
    <section style={{
      marginBottom: 24, padding: '18px 22px',
      background: 'white', borderRadius: 12,
      border: '1px solid rgba(0,124,195,0.1)',
    }}>
      <p style={{
        fontFamily: 'var(--font-plex)', fontSize: 14, lineHeight: 1.6,
        color: 'var(--text-secondary, #455A64)', margin: 0,
      }}>
        This demo runs the marketplace's flagship multi-agent pipeline. The buyer
        side sends one prompt; the marketplace discovers agents on the live CDS,
        asks the planner what skills are needed, then executes a controlled
        2-step pipeline: <strong>General Tecla Industries</strong> summarizes
        the document (India, English/Hindi expertise), then <strong>Serg Ops</strong>
        extracts structured entities from the summary (Mexico). Each hop uses
        the real Beckn v2 flow (discover → select → init → confirm → status)
        and every payload is validated against the agent's declared JSON Schema
        at the marketplace boundary.
      </p>
    </section>
  );
}

function PipelineSpec({ spec }: { spec: DemoSpec }) {
  return (
    <section style={{ marginBottom: 24 }}>
      <SectionLabel>PIPELINE CONTRACT</SectionLabel>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {spec.pipeline.map((step, i) => (
          <div key={step.step_id} style={{ flex: '1 1 320px', display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              background: 'white',
              border: '1px solid rgba(0,124,195,0.12)',
              borderRadius: 12, padding: '14px 16px', flex: 1,
            }}>
              <div style={{
                fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
                color: 'var(--text-tertiary, #78909C)', fontWeight: 700, marginBottom: 4,
              }}>
                STEP {i + 1} · {step.skill_id.toUpperCase()}
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary, #102027)' }}>
                {step.agent_id}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary, #455A64)', marginTop: 2 }}>
                {step.bpp_id}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary, #455A64)', marginTop: 8, lineHeight: 1.5 }}>
                {step.description}
              </div>
            </div>
            {i < spec.pipeline.length - 1 && (
              <div style={{ fontSize: 20, color: 'var(--text-tertiary, #78909C)', flexShrink: 0 }}>→</div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function DocumentInput({
  value, onChange, disabled,
}: { value: string; onChange: (v: string) => void; disabled: boolean }) {
  return (
    <section style={{ marginBottom: 16 }}>
      <SectionLabel>INPUT DOCUMENT</SectionLabel>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={12}
        style={{
          width: '100%', padding: '14px 16px',
          background: 'white', borderRadius: 12,
          border: '1px solid rgba(0,124,195,0.12)',
          fontFamily: 'var(--font-mono, "SF Mono", monospace)',
          fontSize: 12, lineHeight: 1.6,
          color: 'var(--text-primary, #102027)',
          resize: 'vertical', outline: 'none',
        }}
      />
    </section>
  );
}

function RunButton({
  onClick, loading, disabled,
}: { onClick: () => void; loading: boolean; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        padding: '12px 28px',
        background: loading || disabled
          ? 'rgba(0,124,195,0.08)'
          : 'var(--infosys-cobalt, #007CC3)',
        color: loading || disabled ? 'var(--text-tertiary, #78909C)' : '#fff',
        border: 'none', borderRadius: 10,
        fontFamily: 'var(--font-plex)', fontSize: 14, fontWeight: 600,
        cursor: loading || disabled ? 'not-allowed' : 'pointer',
        boxShadow: loading || disabled ? 'none' : '0 2px 12px rgba(0,124,195,0.3)',
        marginBottom: 24,
      }}
    >
      {loading ? '🔄 Running pipeline…' : '▶ Run Pipeline'}
    </button>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: '12px 16px', background: 'rgba(198,40,40,0.08)',
      border: '1px solid rgba(198,40,40,0.2)', borderRadius: 8,
      color: 'var(--trust-low, #C62828)', fontSize: 13,
      marginBottom: 16,
    }}>
      {message}
    </div>
  );
}

function ResultsSection({
  loading, result, spec,
}: {
  loading: boolean;
  result: DemoResult | null;
  spec: DemoSpec | null;
}) {
  return (
    <section>
      <SectionLabel>EXECUTION TRACE</SectionLabel>

      {result && <DiscoverPlannerRow result={result} />}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
        {(loading && !result) && (
          spec?.pipeline.map((s) => (
            <StepCardPending key={s.step_id} stepId={s.step_id} agentId={s.agent_id} bppId={s.bpp_id} />
          ))
        )}
        {result?.steps.map((s) => (
          <StepCard key={s.step_id} step={s} />
        ))}
      </div>

      {result?.overall_status === 'COMPLETED' && result.final_output && (
        <FinalOutput out={result.final_output} />
      )}
    </section>
  );
}

function DiscoverPlannerRow({ result }: { result: DemoResult }) {
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 4 }}>
      <Pill
        label="DISCOVER"
        primary={`${result.discover.catalogs_found} catalogs · ${result.discover.agents_seen} agents`}
        secondary={
          result.discover.agents_required_present
            ? '✓ both required agents in catalog'
            : '⚠ required agent missing'
        }
        ok={result.discover.agents_required_present}
        ms={result.discover.duration_ms}
      />
      <Pill
        label="PLANNER"
        primary={
          result.planner.used
            ? `✓ skills extracted: ${result.planner.skills.join(', ')}`
            : 'Fallback: canonical pipeline'
        }
        secondary={result.planner.fallback_reason || result.planner.error || ''}
        ok={result.planner.used}
        ms={0}
      />
    </div>
  );
}

function Pill({
  label, primary, secondary, ok, ms,
}: {
  label: string; primary: string; secondary: string; ok: boolean; ms: number;
}) {
  return (
    <div style={{
      flex: '1 1 320px',
      background: 'white',
      border: `1px solid ${ok ? 'rgba(0,135,90,0.2)' : 'rgba(245,180,0,0.25)'}`,
      borderLeft: `3px solid ${ok ? 'var(--trust-high, #00875A)' : '#F5B400'}`,
      borderRadius: 10, padding: '12px 14px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
        color: 'var(--text-tertiary, #78909C)', fontWeight: 700, marginBottom: 4,
      }}>
        <span>{label}</span>
        {ms > 0 && <span>{ms}ms</span>}
      </div>
      <div style={{
        fontSize: 13, fontWeight: 600, color: 'var(--text-primary, #102027)',
      }}>
        {primary}
      </div>
      {secondary && (
        <div style={{
          fontSize: 11, color: 'var(--text-tertiary, #78909C)', marginTop: 4, lineHeight: 1.4,
        }}>
          {secondary}
        </div>
      )}
    </div>
  );
}

function StepCardPending({ stepId, agentId, bppId }: { stepId: string; agentId: string; bppId: string }) {
  return (
    <div style={{
      background: 'white', borderRadius: 12,
      border: '1px solid rgba(0,124,195,0.08)',
      borderLeft: '3px solid rgba(0,124,195,0.4)',
      padding: '14px 16px',
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{
        width: 20, height: 20, borderRadius: '50%',
        border: '2px solid rgba(0,124,195,0.25)',
        borderTopColor: 'var(--infosys-cobalt, #007CC3)',
        animation: 'spin 0.8s linear infinite',
      }} />
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{stepId.toUpperCase()} · {agentId}</div>
        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>{bppId} · running…</div>
      </div>
    </div>
  );
}

function StepCard({ step }: { step: StepTrace }) {
  const ok = step.status === 'COMPLETED';
  return (
    <div style={{
      background: 'white', borderRadius: 12,
      border: `1px solid ${ok ? 'rgba(0,135,90,0.18)' : 'rgba(198,40,40,0.2)'}`,
      borderLeft: `3px solid ${ok ? 'var(--trust-high, #00875A)' : 'var(--trust-low, #C62828)'}`,
      padding: '16px 18px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 8,
      }}>
        <div>
          <div style={{
            fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
            color: ok ? 'var(--trust-high, #00875A)' : 'var(--trust-low, #C62828)',
            fontWeight: 700,
          }}>
            {step.step_id.toUpperCase()} · {step.status}
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary, #102027)' }}>
            {step.agent_id}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary, #78909C)', marginTop: 2 }}>
            {step.bpp_id} · skill: {step.skill_id}
          </div>
        </div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {step.duration_ms}ms
          {step.transaction_id && (
            <span style={{ marginLeft: 10, color: 'var(--text-tertiary)' }}>
              txn={step.transaction_id.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      <div style={{
        display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap',
      }}>
        <ValidationChip label="Input schema" ok={step.input_validation.ok} errors={step.input_validation.errors} />
        <ValidationChip label="Output schema" ok={step.output_validation.ok} errors={step.output_validation.errors} />
      </div>

      {step.failure_reason && (
        <div style={{
          marginTop: 10, padding: '8px 12px',
          background: 'rgba(198,40,40,0.06)', borderRadius: 6,
          color: 'var(--trust-low, #C62828)', fontSize: 12,
        }}>
          {step.failure_reason}
        </div>
      )}

      {step.status === 'COMPLETED' && step.output_payload != null && (
        <details style={{ marginTop: 10 }}>
          <summary style={{
            fontSize: 11, letterSpacing: '0.04em', cursor: 'pointer',
            color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)',
          }}>
            output payload
          </summary>
          <pre style={{
            margin: '8px 0 0', padding: '10px 12px',
            background: '#FAFCFE',
            border: '1px solid rgba(0,124,195,0.06)',
            borderRadius: 6, fontSize: 11, lineHeight: 1.5,
            maxHeight: 240, overflow: 'auto',
            color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
          }}>
            {JSON.stringify(step.output_payload, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function ValidationChip({
  label, ok, errors,
}: { label: string; ok: boolean; errors: Array<{ message: string; rule: string }> }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 14,
      background: ok ? 'rgba(0,135,90,0.08)' : 'rgba(198,40,40,0.08)',
      color: ok ? 'var(--trust-high, #00875A)' : 'var(--trust-low, #C62828)',
      fontSize: 11, fontWeight: 600,
    }}
      title={ok ? '' : errors.map(e => `${e.rule}: ${e.message}`).join('\n')}
    >
      {ok ? '✓' : '✗'} {label}
    </div>
  );
}

function FinalOutput({
  out,
}: {
  out: NonNullable<DemoResult['final_output']>;
}) {
  return (
    <section style={{ marginTop: 24 }}>
      <SectionLabel>FINAL OUTPUT</SectionLabel>
      <div style={{
        background: 'white', borderRadius: 12,
        border: '1px solid rgba(0,124,195,0.12)',
        borderTop: '3px solid var(--infosys-cobalt, #007CC3)',
        padding: '20px 22px',
      }}>
        {out.summary && (
          <>
            <SubLabel>SUMMARY</SubLabel>
            <p style={{
              fontFamily: 'var(--font-plex)', fontSize: 14, lineHeight: 1.7,
              color: 'var(--text-primary, #102027)', margin: '6px 0 20px',
            }}>
              {out.summary}
            </p>
          </>
        )}

        {out.key_points && out.key_points.length > 0 && (
          <>
            <SubLabel>KEY POINTS</SubLabel>
            <ul style={{
              margin: '6px 0 20px', paddingLeft: 22,
              fontFamily: 'var(--font-plex)', fontSize: 13, lineHeight: 1.7,
              color: 'var(--text-primary, #102027)',
            }}>
              {out.key_points.map((kp, i) => (
                <li key={i}>{kp}</li>
              ))}
            </ul>
          </>
        )}

        {out.entities && (
          <>
            <SubLabel>STRUCTURED ENTITIES</SubLabel>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 14, marginTop: 8,
            }}>
              <EntityList label="Organizations" items={out.entities.organizations} />
              <EntityList label="Dates" items={out.entities.dates} />
              <EntityList label="Regulatory refs" items={out.entities.regulatory_references} />
              <EntityList label="Monetary amounts" items={out.entities.monetary_amounts} />
              <EntityList label="Obligations" items={out.entities.obligations} />
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function EntityList({ label, items }: { label: string; items?: string[] }) {
  const list = items || [];
  return (
    <div style={{
      background: '#FAFCFE', border: '1px solid rgba(0,124,195,0.08)',
      borderRadius: 8, padding: '10px 12px',
    }}>
      <div style={{
        fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
        color: 'var(--text-tertiary, #78909C)', fontWeight: 700, marginBottom: 6,
      }}>
        {label.toUpperCase()}
      </div>
      {list.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>—</div>
      ) : (
        <ul style={{
          margin: 0, paddingLeft: 16, listStyle: 'disc',
          fontSize: 12, lineHeight: 1.6, color: 'var(--text-primary, #102027)',
        }}>
          {list.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
      color: 'var(--text-tertiary, #78909C)', fontWeight: 700, marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

function SubLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)',
      color: 'var(--text-tertiary, #78909C)', fontWeight: 700,
    }}>
      {children}
    </div>
  );
}
