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

  // Flatten every catalog (one per BPP) into a single ranked list.
  // Within a catalog the CDS already ordered by semantic similarity.
  const all: DiscoveredAgent[] = [];
  for (const catalog of msg.catalogs) {
    const providerName =
      catalog.provider?.descriptor?.name ||
      catalog.descriptor?.name ||
      'Unknown Provider';
    const resources: ResourceRaw[] = (catalog.resources ?? []) as ResourceRaw[];
    const offers: OfferRaw[] = (catalog.offers ?? []) as OfferRaw[];

    // resourceId → offerId, used when the buyer eventually selects.
    const offerMap = new Map<string, string>();
    for (const o of offers) {
      for (const rid of o.resourceIds ?? []) {
        offerMap.set(rid, o.id);
      }
    }

    for (const r of resources) {
      const ra = r.resourceAttributes ?? {};
      const pricing = (ra.pricing ?? {}) as Record<string, string | number>;
      const sla = (ra.sla ?? {}) as Record<string, number>;
      const caps = (ra.capabilities ?? {}) as Record<string, unknown>;
      const skills: Skill[] = (ra.skills ?? []) as Skill[];

      all.push({
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
        // Use the catalog's provider (canonical for the BPP) over any
        // provider field nested inside agent_facts (often a self-reference).
        provider: providerName,
      });
    }
  }
  return all;
}

// ── Index introspection ────────────────────────────────────

/**
 * Quick stats from the CDS — total currently-published agents.
 * Used by the search page hero ("N agents available") so the UI does
 * not have to fire a discover just to know how many agents exist.
 */
export async function getCdsStats(): Promise<{ totalAgents: number }> {
  const CDS = (typeof window !== 'undefined'
    ? 'http://localhost:8090'
    : 'http://mock-network:8090');
  try {
    const res = await fetch(`${CDS}/cds/stats`);
    if (!res.ok) return { totalAgents: 0 };
    const data = await res.json();
    return { totalAgents: Number(data?.index?.current_agents_total ?? 0) };
  } catch {
    return { totalAgents: 0 };
  }
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

export { iconForAgent };

// ── Raw types for parsing ──────────────────────────────────

interface CatalogRaw {
  id: string;
  resources?: ResourceRaw[];
  offers?: OfferRaw[];
  descriptor?: { name: string; shortDesc?: string };
  provider?: {
    id: string;
    descriptor?: { name: string; shortDesc?: string };
  };
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
  };
}

interface OfferRaw {
  id: string;
  descriptor?: { name: string };
  resourceIds?: string[];
}
