"""Multi-stage retrieval over ``agent_versions``.

Pipeline:

  Stage 1 — Hard filters (SQL WHERE)
            jurisdiction, languages, capabilities, currency, price, SLA.
            All filters are ANDed; an omitted filter is a no-op.
            Reduces the candidate set BEFORE the vector scan so the HNSW
            index walks a small subset.

  Stage 2 — Semantic ranking (pgvector cosine)
            When the query carries a ``text_search``, we embed it once and
            order by ``embedding <=> $query_vec``. Without text_search we
            fall back to ``published_at DESC`` (most recently published
            agents first) which is a sensible default for browse-style
            requests.

The composite scoring described in the briefing
(``semantic × 0.6 + freshness × 0.2 + health × 0.2``) is deliberately
NOT implemented here — that needs the Registry health signal joined in,
which is a Pieza 4 concern. We expose only ``similarity`` for now and
sort by it; future work plugs the rest in without changing the SQL
shape (the candidate set stays the same).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.db.pool import get_pool
from app.discover.models import DiscoverQuery, StructuredFilters
from app.embeddings.service import EmbeddingService, get_default_service

logger = logging.getLogger(__name__)


_CANDIDATE_COLUMNS = """
    id, agent_urn, version, bpp_subscriber_id, beckn_id, agentfacts_id,
    label, description, jurisdiction, languages, capability_tags,
    input_modes, output_modes,
    pricing_currency, pricing_value, sla_max_latency_ms,
    agent_facts, published_at
"""


def build_filter_params(filters: StructuredFilters) -> dict:
    """Translate the structured filter object into the keyword arguments
    accepted by the retrieval SQL below.

    Pulled out as a pure function so we can unit-test the mapping
    without touching Postgres.

    Returns a dict with eight keys (one per filter dimension) where each
    value is either the typed bound or ``None`` to mean "no constraint".
    """
    return {
        "jurisdiction": filters.jurisdiction or None,
        "languages": list(filters.languages) if filters.languages else None,
        "capabilities": list(filters.capabilities) if filters.capabilities else None,
        "currency": filters.currency or None,
        "max_price_value": float(filters.max_price_value)
            if filters.max_price_value is not None else None,
        "max_latency_ms": int(filters.max_latency_ms)
            if filters.max_latency_ms is not None else None,
    }


def _parse_jsonb(value) -> dict:
    """``agent_facts`` may come back as str or dict depending on codec wiring."""
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


async def retrieve_candidates(
    query: DiscoverQuery,
    *,
    embedder: Optional[EmbeddingService] = None,
) -> list[dict]:
    """Run the full pipeline and return candidate rows ranked by similarity.

    Each row is a dict shaped for ``service.assemble_catalogs``:

        { bpp_subscriber_id, beckn_id, label, description,
          agent_facts, similarity, ... }

    When ``query.text_search`` is empty the similarity is 0.0 for all
    rows and ordering falls back to ``published_at DESC``.
    """
    embedder = embedder or get_default_service()

    query_vec: Optional[list[float]] = None
    if query.text_search:
        query_vec = embedder.embed(query.text_search)

    params = build_filter_params(query.filters)

    sql = f"""
        SELECT
            {_CANDIDATE_COLUMNS},
            CASE
                WHEN $1::vector IS NULL THEN 0.0
                ELSE 1 - (embedding <=> $1)
            END AS similarity
        FROM agent_versions
        WHERE status = 'current'
          AND ($2::text     IS NULL OR jurisdiction       = $2)
          AND ($3::text[]   IS NULL OR languages          @> $3)
          AND ($4::text[]   IS NULL OR capability_tags    @> $4)
          AND ($5::char(3)  IS NULL OR pricing_currency   = $5)
          AND ($6::numeric  IS NULL OR pricing_value     <= $6)
          AND ($7::int      IS NULL OR sla_max_latency_ms<= $7)
        ORDER BY similarity DESC, published_at DESC
        LIMIT $8
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            sql,
            query_vec,
            params["jurisdiction"],
            params["languages"],
            params["capabilities"],
            params["currency"],
            params["max_price_value"],
            params["max_latency_ms"],
            query.limit,
        )

    results: list[dict] = []
    for r in rows:
        d = dict(r)
        d["agent_facts"] = _parse_jsonb(d.get("agent_facts"))
        d["similarity"] = float(d.get("similarity") or 0.0)
        d["languages"] = list(d.get("languages") or [])
        d["capability_tags"] = list(d.get("capability_tags") or [])
        d["input_modes"] = list(d.get("input_modes") or [])
        d["output_modes"] = list(d.get("output_modes") or [])
        results.append(d)
    return results
