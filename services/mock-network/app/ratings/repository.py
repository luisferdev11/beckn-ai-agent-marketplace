"""Postgres access for the ratings aggregator.

Owns the ``agent_ratings_agg`` table — one row per (bpp_subscriber_id,
agent_beckn_id) carrying a running sum/count and the rolling average.
Discover reads ``avg_score`` and ``rating_count`` from this table to
compute the quality component of the composite score.

Tests monkeypatch the two public functions in ``tests/conftest.py``
with an in-memory fake so the route layer never touches Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.db.pool import get_pool


async def ingest_rating(
    *,
    bpp_subscriber_id: str,
    agent_beckn_id: str,
    score: float,
    rated_at: Optional[datetime] = None,
) -> dict:
    """Add one rating event to the rolling aggregate.

    Uses ``INSERT ... ON CONFLICT DO UPDATE`` so the per-agent row is
    upserted atomically. Storage is raw-sum + count; ``avg_score`` is
    recomputed on each write so the column can be indexed for ORDER BY
    without an extra read step.
    """
    rated_at = rated_at or datetime.now(timezone.utc)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO agent_ratings_agg
            (bpp_subscriber_id, agent_beckn_id,
             rating_count, rating_sum, avg_score,
             last_rated_at, last_updated_at)
        VALUES ($1, $2, 1, $3, $3, $4, $4)
        ON CONFLICT (bpp_subscriber_id, agent_beckn_id) DO UPDATE
        SET rating_count    = agent_ratings_agg.rating_count + 1,
            rating_sum      = agent_ratings_agg.rating_sum + EXCLUDED.rating_sum,
            avg_score       = (agent_ratings_agg.rating_sum + EXCLUDED.rating_sum)
                              / (agent_ratings_agg.rating_count + 1),
            last_rated_at   = EXCLUDED.last_rated_at,
            last_updated_at = EXCLUDED.last_updated_at
        RETURNING bpp_subscriber_id, agent_beckn_id,
                  rating_count, rating_sum, avg_score,
                  last_rated_at, last_updated_at
        """,
        bpp_subscriber_id, agent_beckn_id, score, rated_at,
    )
    return dict(row) if row else {}


async def get_aggregate(*, bpp_subscriber_id: str, agent_beckn_id: str) -> Optional[dict]:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT bpp_subscriber_id, agent_beckn_id, rating_count, rating_sum,
               avg_score, last_rated_at, last_updated_at
        FROM agent_ratings_agg
        WHERE bpp_subscriber_id = $1 AND agent_beckn_id = $2
        """,
        bpp_subscriber_id, agent_beckn_id,
    )
    return dict(row) if row else None
