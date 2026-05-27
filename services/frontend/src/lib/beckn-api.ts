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
  };
}

interface OfferRaw {
  id: string;
  descriptor?: { name: string };
  resourceIds?: string[];
}
