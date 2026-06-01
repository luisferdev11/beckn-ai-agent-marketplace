/**
 * Demo API client — talks to the BAP's /api/demo surface.
 *
 * The demo runs a controlled cross-BPP pipeline (Tecla legal summarizer
 * → Serg structured extractor) with real Beckn flow at every hop and
 * JSON Schema validation between steps. This module is just the
 * typed shim; the UI page renders the trace.
 */

const API = (typeof window !== 'undefined'
  ? 'http://localhost:3001'
  : 'http://bap-marketplace:3001') + '/api/demo';

// ── /spec response ─────────────────────────────────────────────────

export interface DemoStepSpec {
  step_id: string;
  skill_id: string;
  agent_id: string;
  bpp_id: string;
  bpp_uri: string;
  description: string;
  // JSON Schema (draft-2020-12). Surfaced so the UI can show
  // "this is the contract this agent declares to honour".
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface DemoSpec {
  prompt: string;
  sample_document: string;
  pipeline: DemoStepSpec[];
  step_input_mapping: Record<string, string>;
}

export async function fetchDemoSpec(): Promise<DemoSpec> {
  const res = await fetch(`${API}/spec`);
  if (!res.ok) throw new Error(`Failed to load demo spec (${res.status})`);
  return res.json();
}

// ── /legal-pipeline response ───────────────────────────────────────

export interface ValidationReport {
  ok: boolean;
  errors: Array<{ location: string; message: string; rule: string }>;
}

export interface StepTrace {
  step_id: string;
  skill_id: string;
  agent_id: string;
  bpp_id: string;
  transaction_id: string | null;
  started_at_ms: number;
  duration_ms: number;
  status: 'COMPLETED' | 'FAILED' | 'PENDING';
  input_payload: Record<string, unknown>;
  input_validation: ValidationReport;
  // The agent's structured output — shape depends on the agent.
  output_payload: unknown;
  output_validation: ValidationReport;
  failure_reason: string | null;
}

export interface DiscoverTrace {
  transaction_id: string | null;
  catalogs_found: number;
  agents_seen: number;
  agents_required_present: boolean;
  duration_ms: number;
}

export interface PlannerTrace {
  skills: string[];
  // The plan object the planner returned, or null on failure.
  plan: Record<string, unknown> | null;
  error: string | null;
  used: boolean;
  fallback_reason: string | null;
}

export interface DemoResult {
  overall_status: 'COMPLETED' | 'FAILED' | 'PENDING';
  discover: DiscoverTrace;
  planner: PlannerTrace;
  steps: StepTrace[];
  final_output: {
    summary?: string;
    key_points?: string[];
    language?: string;
    entities?: {
      organizations?: string[];
      dates?: string[];
      regulatory_references?: string[];
      monetary_amounts?: string[];
      obligations?: string[];
    };
  } | null;
}

export async function runLegalPipeline(
  document: string,
  language = 'en',
): Promise<DemoResult> {
  const res = await fetch(`${API}/legal-pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document, language }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Pipeline run failed (${res.status}): ${detail.slice(0, 240)}`);
  }
  return res.json();
}
