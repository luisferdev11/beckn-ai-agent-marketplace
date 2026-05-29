"""Multi-stage retrieval over ``agent_versions``.

Pipeline:

  Stage 1 — Hard filters (SQL WHERE)
            jurisdiction, languages, capabilities, currency, price, SLA.
            All filters are ANDed; an omitted filter is a no-op.
            Reduces the candidate set BEFORE the vector scan so the HNSW
            index walks a small subset.

  Stage 2 — Semantic ranking (pgvector cosine)
            When the query carries a ``text_search``, we embed it once and
            order by ``embedding <=> $query_vec``. Without text_search the
            ``similarity`` component is 0.0 for every row and ordering
            collapses onto freshness + health.

  Stage 3 — Composite scoring
            ``score = 0.6 * semantic + 0.2 * freshness + 0.2 * health``
            Computed inline in SQL using the constants from
            ``app.discover.scoring`` so the formula has a single source of
            truth. The JOIN against ``subscribers`` brings in the
            Registry health signal. ``LEFT JOIN`` is intentional: an
            agent indexed for a deprecated BPP still surfaces — its
            ``bpp_health`` falls back to ``unknown`` and gets the
            neutral 0.5 contribution.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.db.pool import get_pool
from app.discover.models import DiscoverQuery, StructuredFilters
from app.discover.scoring import (
    FRESHNESS_WEIGHT,
    FRESHNESS_WINDOW_DAYS,
    HEALTH_WEIGHT,
    QUALITY_DEFAULT,
    QUALITY_SCALE_MAX,
    QUALITY_SCALE_MIN,
    QUALITY_WEIGHT,
    SEMANTIC_WEIGHT,
)
from app.embeddings.service import EmbeddingService, get_default_service

logger = logging.getLogger(__name__)


_CANDIDATE_COLUMNS = """
    av.id, av.agent_urn, av.version, av.bpp_subscriber_id, av.beckn_id, av.agentfacts_id,
    av.label, av.description, av.jurisdiction, av.languages, av.capability_tags,
    av.input_modes, av.output_modes,
    av.pricing_currency, av.pricing_value, av.sla_max_latency_ms,
    av.agent_facts, av.published_at
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

    # Composite-score SQL.
    #
    # ``ranked`` projects per-row similarity, freshness, and a numeric
    # health value from the Registry. The outer SELECT adds the composite
    # ``score`` using the same weights as ``app.discover.scoring`` so the
    # formula stays single-sourced (weights are baked into the string;
    # changing them in scoring.py is a one-place edit that picks up here
    # via the f-string).
    #
    # GREATEST/LEAST clamp pgvector's similarity into 0..1 — cosine
    # similarity occasionally drifts microscopically outside that range
    # for unit-vector inputs.
    sql = f"""
        WITH ranked AS (
            SELECT
                {_CANDIDATE_COLUMNS},
                CASE
                    WHEN $1::vector IS NULL THEN 0.0::float8
                    ELSE GREATEST(0.0::float8, LEAST(1.0::float8, 1 - (av.embedding <=> $1)))
                END AS similarity,
                COALESCE(s.health, 'unknown') AS bpp_health,
                GREATEST(0.0::float8, LEAST(1.0::float8,
                    1 - EXTRACT(EPOCH FROM (NOW() - av.published_at))
                        / ({FRESHNESS_WINDOW_DAYS}::float8 * 86400.0)
                )) AS freshness,
                CASE COALESCE(s.health, 'unknown')
                    WHEN 'healthy'   THEN 1.0::float8
                    WHEN 'degraded'  THEN 0.5::float8
                    WHEN 'unhealthy' THEN 0.0::float8
                    ELSE 0.5::float8
                END AS health_value,
                -- Quality: rolling user-rating average normalised to 0..1.
                -- LEFT JOIN: agents with no ratings yet get NULL → neutral
                -- default below, matching scoring.quality_score().
                COALESCE(r.rating_count, 0) AS rating_count,
                CASE
                    WHEN r.rating_count IS NULL OR r.rating_count = 0
                        THEN {QUALITY_DEFAULT}::float8
                    ELSE GREATEST(0.0::float8, LEAST(1.0::float8,
                        (r.avg_score - {QUALITY_SCALE_MIN}::float8)
                        / ({QUALITY_SCALE_MAX}::float8 - {QUALITY_SCALE_MIN}::float8)
                    ))
                END AS quality_value
            FROM agent_versions av
            LEFT JOIN subscribers s ON av.bpp_subscriber_id = s.subscriber_id
            LEFT JOIN agent_ratings_agg r
                   ON r.bpp_subscriber_id = av.bpp_subscriber_id
                  AND r.agent_beckn_id    = av.beckn_id
            WHERE av.status = 'current'
              AND ($2::text     IS NULL OR av.jurisdiction       = $2)
              AND ($3::text[]   IS NULL OR av.languages          @> $3)
              AND ($4::text[]   IS NULL OR av.capability_tags    @> $4)
              AND ($5::char(3)  IS NULL OR av.pricing_currency   = $5)
              AND ($6::numeric  IS NULL OR av.pricing_value     <= $6)
              AND ($7::int      IS NULL OR av.sla_max_latency_ms<= $7)
        )
        SELECT
            ranked.*,
            ({SEMANTIC_WEIGHT}::float8 * similarity
             + {FRESHNESS_WEIGHT}::float8 * freshness
             + {HEALTH_WEIGHT}::float8 * health_value
             + {QUALITY_WEIGHT}::float8 * quality_value
            ) AS score
        FROM ranked
        ORDER BY score DESC, published_at DESC
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
        d["freshness"] = float(d.get("freshness") or 0.0)
        d["health_value"] = float(d.get("health_value") or 0.5)
        d["quality_value"] = float(d.get("quality_value") or QUALITY_DEFAULT)
        d["rating_count"] = int(d.get("rating_count") or 0)
        d["score"] = float(d.get("score") or 0.0)
        d["languages"] = list(d.get("languages") or [])
        d["capability_tags"] = list(d.get("capability_tags") or [])
        d["input_modes"] = list(d.get("input_modes") or [])
        d["output_modes"] = list(d.get("output_modes") or [])
        results.append(d)
    return results
