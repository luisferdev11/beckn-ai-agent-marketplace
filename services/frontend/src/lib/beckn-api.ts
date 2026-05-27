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

export async function discover(query?: string): Promise<DiscoveredAgent[]> {
  const res = await fetch(`${API}/contracts/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query || undefined }),
  });
  const { transactionId } = await res.json();
  const cb = await pollCallback(transactionId, 'on_discover');

  const msg = cb.message as { catalogs?: CatalogRaw[] };
  if (!msg.catalogs?.length) return [];

  const catalog = msg.catalogs[0];
  const resources: ResourceRaw[] = (catalog.resources ?? []) as ResourceRaw[];
  const offers: OfferRaw[] = (catalog.offers ?? []) as OfferRaw[];

  // Build a map: resourceId → offerId
  const offerMap = new Map<string, string>();
  for (const o of offers) {
    for (const rid of o.resourceIds ?? []) {
      offerMap.set(rid, o.id);
    }
  }

  return resources.map((r): DiscoveredAgent => {
    const ra = r.resourceAttributes ?? {};
    const pricing = (ra.pricing ?? {}) as Record<string, string | number>;
    const sla = (ra.sla ?? {}) as Record<string, number>;
    const caps = (ra.capabilities ?? {}) as Record<string, unknown>;
    const skills: Skill[] = (ra.skills ?? []) as Skill[];

    // Marketplace ranking signals — keys start with underscore on the wire
    // to distinguish them from AgentFacts the BPP declared. Surface them as
    // first-class fields on the agent so the UI can render the breakdown
    // without re-digging into resourceAttributes.
    const marketplaceScore = ra._marketplaceScore;
    const rawComponents = ra._marketplaceScoreComponents as Record<string, unknown> | undefined;
    let scoreComponents: ScoreComponents | undefined;
    if (rawComponents) {
      scoreComponents = {
        semantic: Number(rawComponents.semantic ?? 0),
        freshness: Number(rawComponents.freshness ?? 0),
        health: Number(rawComponents.health ?? 0),
      };
      if (rawComponents.quality !== undefined) {
        scoreComponents.quality = Number(rawComponents.quality);
      }
      if (rawComponents.ratingCount !== undefined) {
        scoreComponents.ratingCount = Number(rawComponents.ratingCount);
      }
    }

    return {
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
      provider: String((ra.provider as Record<string, string>)?.name || 'Unknown Provider'),
      score: marketplaceScore !== undefined ? Number(marketplaceScore) : undefined,
      scoreComponents,
    };
  });
}

export async function selectAgent(
  agentId: string,
  offerId: string,
  buyerName = 'Marketplace User',
): Promise<SelectResult> {
  const res = await fetch(`${API}/contracts/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, offer_id: offerId, buyer_name: buyerName }),
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

export { iconForAgent };

// ── Raw types for parsing ──────────────────────────────────

interface CatalogRaw {
  id: string;
  resources?: ResourceRaw[];
  offers?: OfferRaw[];
  descriptor?: { name: string; shortDesc?: string };
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
