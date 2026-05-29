/**
 * Beckn API client — calls the BAP REST API via the Next.js rewrite proxy.
 * Each action sends a POST, then polls for the async on_* callback.
 */

// In Docker the Next.js rewrite proxy doesn't work in standalone mode,
// so we call the BAP directly from the browser.  The browser can reach
// localhost:3001 when ports are mapped in docker-compose.
const API = (typeof window !== 'undefined' ? 'http://localhost:3001' : 'http://bap-marketplace:3001') + '/api';

// ── Types ──────────────────────────────────────────────────

export interface DiscoveredAgent {
  id: string;
  offerId: string;
  name: string;
  description: string;
  longDesc: string;
  skills: Skill[];
  pricing: { model: string; value: number; currency: string };
  sla: { maxLatencyMs: number; accuracy: number; uptime: number };
  modalities: string[];
  jurisdiction: string | null;
  provider: string;
  // BPP routing — populated from each catalog's ``provider`` block so the
  // BAP knows which BPP to address on subsequent select/init/confirm.
  // Without these the BAP falls back to its statically-configured
  // default BPP and mis-routes any pick that is not the default.
  bppId: string;
  bppUri?: string;
  // Composite ranking exposed by the CDS (mock-network/discover). Optional
  // because older /discover responses won't have these fields yet — the
  // frontend renders the breakdown only when present.
  score?: number;
  scoreComponents?: ScoreComponents;
}

export interface ScoreComponents {
  semantic: number;
  freshness: number;
  health: number;
  // The quality component lands once the rate-end-to-end PR is merged.
  // Until then we treat it as optional.
  quality?: number;
  ratingCount?: number;
}

export interface Skill {
  id: string;
  description: string;
  inputModes?: string[];
  outputModes?: string[];
  supportedLanguages?: string[];
  maxTokens?: number;
  latencyBudgetMs?: number;
}

export interface SelectResult {
  transactionId: string;
  contract: ContractData;
}

export interface ContractData {
  id?: string;
  commitments?: Commitment[];
  consideration?: Consideration[];
  participants?: Participant[];
  performance?: Performance[];
  settlements?: Settlement[];
}

interface Commitment {
  id: string;
  descriptor?: { name: string; code: string };
  status?: { code: string };
  resources?: Resource[];
  offer?: { id: string; resourceIds: string[] };
}

interface Resource {
  id: string;
  descriptor?: { name: string; code?: string; longDesc?: string };
  quantity?: { unitQuantity: number; unitCode: string };
}

interface Consideration {
  id: string;
  price: { value: string; currency: string };
  status?: { code: string };
  breakup?: Array<{ title: string; price: { value: string; currency: string } }>;
}

interface Participant {
  id: string;
  descriptor: { name: string; code: string };
}

interface Performance {
  id: string;
  status?: { code: string; name?: string; shortDesc?: string };
  performanceAttributes?: PerformanceAttributes;
}

export interface PerformanceAttributes {
  '@type': string;
  '@context': string;
  status: string;
  model: string;
  latencyMs: number;
  startedAt: string;
  completedAt: string;
  tokensUsed: { input: number; output: number; total: number };
  result: Record<string, unknown>;
}

interface Settlement {
  id: string;
  status: string;
}

interface RawCallback {
  id: number;
  transaction_id: string;
  action: string;
  context: string | Record<string, unknown>;
  message: string | Record<string, unknown>;
  received_at: string;
  error?: string;
}

// ── Planner types (mirror libs/beckn_models/beckn_models/planning.py) ─

export interface StepRecommendation {
  agent_id: string;
  name: string;
  provider: string;
  cost: number;
  currency: string;
  latency_ms: number;
  reason: string;
}

export interface StepAlternative {
  agent_id: string;
  name: string;
  cost: number;
  latency_ms: number;
  note: string;
}

export interface PlanStep {
  id: string;
  skill_id: string;
  depends_on: string[];
  recommended: StepRecommendation;
  alternatives: StepAlternative[];
  input_mapping: Record<string, string>;
}

export interface PlanEstimates {
  total_cost: number;
  currency: string;
  max_latency_ms: number;
  steps_count: number;
}

export interface Plan {
  summary: string;
  steps: PlanStep[];
  estimates: PlanEstimates;
  on_error: string;
}

export interface PlanResponse {
  plan?: Plan | null;
  error?: string | null;
  transaction_ids: string[];
}

// ── Helpers ────────────────────────────────────────────────

function parseJson(v: string | Record<string, unknown>): Record<string, unknown> {
  if (typeof v === 'object') return v as Record<string, unknown>;
  try { return JSON.parse(v); } catch { return {}; }
}

async function pollCallback(
  txnId: string,
  expectedAction: string,
  maxWaitMs = 30_000,
  intervalMs = 1_000,
  afterId = 0,
): Promise<{ id: number; context: Record<string, unknown>; message: Record<string, unknown> }> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API}/callbacks/ultimo?transaction_id=${txnId}`);
    const data: RawCallback = await res.json();
    if (data.action === expectedAction && data.id > afterId) {
      return {
        id: data.id,
        context: parseJson(data.context),
        message: parseJson(data.message),
      };
    }
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error(`Timeout waiting for ${expectedAction} (txn=${txnId.slice(0, 8)})`);
}

function iconForAgent(name: string): string {
  const n = name.toLowerCase();
  if (n.includes('summar') || n.includes('legal')) return '📝';
  if (n.includes('code') || n.includes('review')) return '🔍';
  if (n.includes('extract') || n.includes('invoice') || n.includes('data')) return '📊';
  if (n.includes('groq') || n.includes('text') || n.includes('generat')) return '💬';
  return '🤖';
}

// ── API calls ──────────────────────────────────────────────

/**
 * Discover agents matching a natural-language prompt.
 *
 * Calls BAP /api/contracts/discover with ``intent_text`` (preferred semantic
 * path — gets embedded server-side and ranked by cosine similarity). After
 * the sync ACK, polls /api/callbacks/ultimo for the asynchronous on_discover
 * callback and flattens every catalog (one per BPP) into a single ranked list.
 *
 * The CDS returns one on_discover envelope with N catalogs, one per matching
 * provider. We flatten across providers while preserving per-catalog
 * ordering (the CDS already ranks within each catalog by semantic similarity).
 *
 * @param prompt  Natural-language task description. Empty string returns
 *                most-recently-published agents (browse mode).
 */
export async function discover(prompt?: string): Promise<DiscoveredAgent[]> {
  const intentText = (prompt ?? '').trim();
  const res = await fetch(`${API}/contracts/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(intentText ? { intent_text: intentText } : {}),
  });
  const { transactionId } = await res.json();
  const cb = await pollCallback(transactionId, 'on_discover');

  const msg = cb.message as { catalogs?: CatalogRaw[] };
  if (!msg.catalogs?.length) return [];

  // Federated discover: the CDS returns one catalog per BPP that has a
  // matching agent. We flatten resources across catalogs and tag each
  // one with its source BPP so the buyer's subsequent select knows
  // where to route. Previously this only read ``catalogs[0]`` which
  // silently dropped every BPP other than the first — and after the
  // composite-scoring change, "first" depends on max-score-per-BPP, so
  // which BPP got dropped became request-dependent.
  const out: DiscoveredAgent[] = [];
  for (const catalog of msg.catalogs) {
    const resources: ResourceRaw[] = (catalog.resources ?? []) as ResourceRaw[];
    const offers: OfferRaw[] = (catalog.offers ?? []) as OfferRaw[];

    const offerMap = new Map<string, string>();
    for (const o of offers) {
      for (const rid of o.resourceIds ?? []) {
        offerMap.set(rid, o.id);
      }
    }

    // bppId/bppUri come from the catalog-level provider block populated
    // by mock-network/discover/service.py:assemble_catalogs. bppId is
    // the subscriber id (e.g. "bpp-serg.example.com"); bppUri is the
    // ONIX endpoint pulled from the Registry (network-local extension
    // under provider.endpoints.beckn).
    const provider = catalog.provider as CatalogProviderRaw | undefined;
    const bppId = String(provider?.id ?? '');
    const bppUri = (provider?.endpoints?.beckn ?? undefined) as string | undefined;
    const providerName = provider?.descriptor?.name ?? '';

    for (const r of resources) {
      const ra = r.resourceAttributes ?? {};
      const pricing = (ra.pricing ?? {}) as Record<string, string | number>;
      const sla = (ra.sla ?? {}) as Record<string, number>;
      const caps = (ra.capabilities ?? {}) as Record<string, unknown>;
      const skills: Skill[] = (ra.skills ?? []) as Skill[];

      out.push({
        id: r.id,
        offerId: offerMap.get(r.id) ?? `offer-${r.id}`,
        name: String(ra.label || r.descriptor?.name || `Agent ${r.id}`),
        description: String(r.descriptor?.shortDesc || ra.description || ''),
        longDesc: String(r.descriptor?.longDesc || ra.description || ''),
        skills,
        pricing: {
          model: String(pricing.model || pricing.type || 'per_task'),
          value: Number(pricing.value ?? 0),
          currency: String(pricing.currency ?? 'INR'),
        },
        sla: {
          maxLatencyMs: Number(sla.maxLatencyMs ?? 10_000),
          accuracy: Number(sla.accuracy ?? 0),
          uptime: Number(sla.uptime ?? 0),
        },
        modalities: (caps.modalities ?? ['text']) as string[],
        jurisdiction: ra.jurisdiction ? String(ra.jurisdiction) : null,
        // Fall back to AgentFacts ``provider.name`` if the catalog
        // didn't include a provider name (e.g. dropped subscriber row).
        provider:
          providerName ||
          String((ra.provider as Record<string, string>)?.name || 'Unknown Provider'),
        bppId,
        bppUri,
      });
    }
  }
  return out;
}

export async function selectAgent(
  agentId: string,
  offerId: string,
  options: {
    buyerName?: string;
    bppId?: string;
    bppUri?: string;
  } = {},
): Promise<SelectResult> {
  const body: Record<string, unknown> = {
    agent_id: agentId,
    offer_id: offerId,
    buyer_name: options.buyerName ?? 'Marketplace User',
  };
  // Forward BPP routing so the BAP addresses the right provider. Without
  // these the BAP defaults to its statically-configured BPP_URI and
  // mis-routes selects for any non-default BPP — silent failure mode
  // because the on_select error envelope is not currently bubbled back
  // to the BAP (parked bug #1).
  if (options.bppId) body.bpp_id = options.bppId;
  if (options.bppUri) body.bpp_uri = options.bppUri;

  const res = await fetch(`${API}/contracts/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const { transactionId } = await res.json();
  const cb = await pollCallback(transactionId, 'on_select');
  const contract = (cb.message as { contract?: ContractData }).contract ?? {};
  return { transactionId, contract };
}

export async function initTransaction(txnId: string): Promise<ContractData> {
  await fetch(`${API}/contracts/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transaction_id: txnId }),
  });
  const cb = await pollCallback(txnId, 'on_init');
  return (cb.message as { contract?: ContractData }).contract ?? {};
}

export async function confirmTransaction(txnId: string, prompt?: string): Promise<ContractData> {
  await fetch(`${API}/contracts/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transaction_id: txnId, prompt }),
  });
  const cb = await pollCallback(txnId, 'on_confirm');
  return (cb.message as { contract?: ContractData }).contract ?? {};
}

// Track the last seen on_status callback ID so subsequent calls wait for a FRESH callback
const _lastStatusId: Record<string, number> = {};

export async function pollStatus(txnId: string): Promise<ContractData> {
  const afterId = _lastStatusId[txnId] || 0;
  await fetch(`${API}/contracts/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transaction_id: txnId }),
  });
  const cb = await pollCallback(txnId, 'on_status', 30_000, 1_000, afterId);
  _lastStatusId[txnId] = cb.id;
  return (cb.message as { contract?: ContractData }).contract ?? {};
}

/**
 * Submit a buyer rating against a completed transaction.
 *
 * The BAP endpoint accepts a 1..5 score plus optional free-form
 * feedback. Re-rating the same target on the same transaction
 * overwrites (BAP-side upsert), so callers don't need to track
 * "already rated" state defensively.
 *
 * Returns the on_rate confirmation envelope or throws if the BAP
 * itself rejects the rating (e.g. unknown transaction → 404, score
 * out of range → 422). ONIX-side NACKs return a 200 + NACK body —
 * we surface that as an error so the UI can show a clear failure.
 */
export async function rateContract(
  txnId: string,
  score: number,
  options: { feedback?: string; targetId?: string } = {},
): Promise<{ ack: 'ACK' | 'NACK'; error?: { code: string; message: string } }> {
  const body: Record<string, unknown> = {
    transaction_id: txnId,
    score,
  };
  if (options.feedback) body.feedback = options.feedback;
  if (options.targetId) body.target_id = options.targetId;

  const res = await fetch(`${API}/contracts/rate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Rate failed (${res.status}): ${detail.slice(0, 240)}`);
  }
  const data = await res.json();
  const ack = data?.onix_response?.message?.ack?.status as 'ACK' | 'NACK' | undefined;
  const error = data?.onix_response?.error as { code: string; message: string } | undefined;
  if (ack === 'NACK') {
    throw new Error(`Network rejected the rating: ${error?.code || 'NACK'} — ${error?.message || ''}`);
  }
  return { ack: ack ?? 'ACK', error };
}

/**
 * Compose a multi-step workflow plan from a natural-language prompt.
 *
 * Calls BAP /api/plan, which internally orchestrates:
 *   1. POST /extract-skills on the planner (LLM #1)
 *   2. POST /api/contracts/discover in parallel, one per skill
 *   3. POST /compose-pipeline on the planner (LLM #2 + validator)
 *
 * Unlike discover(), the call is synchronous from the frontend's POV — the
 * BAP holds the request open until the full plan is composed (can take
 * 5-15s due to two LLM hops + discover round-trips). No callback polling.
 *
 * Throws on transport errors or non-2xx responses with a backend-provided
 * detail message. A 2xx with `plan: null` and `error: "..."` means the
 * planner reported a soft failure (e.g. no candidates for some skill) —
 * we surface that as a thrown error too so the UI's error path handles it.
 */
export async function plan(prompt: string): Promise<Plan> {
  const res = await fetch(`${API}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt: prompt.trim(),
      input_format: 'text/plain',
      output_format: 'text/plain',
    }),
  });
  if (!res.ok) {
    let detail = `Plan failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      // Fall through to status-code-only message.
    }
    throw new Error(detail);
  }
  const data = (await res.json()) as PlanResponse;
  if (!data.plan) {
    throw new Error(data.error || 'Planner returned no plan');
  }
  return data.plan;
}

export { iconForAgent };

// ── Raw types for parsing ──────────────────────────────────

interface CatalogRaw {
  id: string;
  resources?: ResourceRaw[];
  offers?: OfferRaw[];
  descriptor?: { name: string; shortDesc?: string };
  provider?: CatalogProviderRaw;
}

interface CatalogProviderRaw {
  id?: string;
  descriptor?: { name?: string; shortDesc?: string };
  endpoints?: { beckn?: string };
}

interface ResourceRaw {
  id: string;
  descriptor?: { name: string; shortDesc?: string; longDesc?: string };
  resourceAttributes?: Record<string, unknown> & {
    label?: string;
    description?: string;
    skills?: unknown[];
    pricing?: Record<string, unknown>;
    sla?: Record<string, number>;
    capabilities?: Record<string, unknown>;
    jurisdiction?: string;
    provider?: { name: string; url?: string };
    _marketplaceScore?: number;
    _marketplaceScoreComponents?: Record<string, unknown>;
  };
}

interface OfferRaw {
  id: string;
  descriptor?: { name: string };
  resourceIds?: string[];
}
