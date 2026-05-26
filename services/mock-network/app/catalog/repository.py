"""Postgres access for the CDS catalog index.

Two surfaces:

  ``record_publish`` / ``update_publish_result``  — audit trail in
    ``published_catalogs``. Used by the on_publish callback to report
    per-catalog stats and by operators to debug bad publishes.

  ``upsert_agent_version``  — index write into ``agent_versions``. Holds
    the version-promotion logic: when a new (agent_urn, version) lands,
    any existing ``current`` row for the same urn flips to ``deprecated``
    inside the same transaction so the partial-unique-index constraint
    is never violated.

The fake in ``tests/conftest.py`` monkeypatches every function here, so
the route layer never touches Postgres in unit/integration tests.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.db.pool import get_pool

logger = logging.getLogger(__name__)


# ─── published_catalogs ─────────────────────────────────────────────


async def record_publish(
    *,
    transaction_id: str,
    message_id: str,
    bpp_subscriber_id: str,
    catalog_id: Optional[str],
    raw_payload: dict,
) -> int:
    """Insert a PENDING audit row and return its primary key."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO published_catalogs
                (transaction_id, message_id, bpp_subscriber_id,
                 catalog_id, raw_payload, status)
            VALUES ($1, $2, $3, $4, $5::jsonb, 'PENDING')
            RETURNING id
            """,
            transaction_id, message_id, bpp_subscriber_id,
            catalog_id, json.dumps(raw_payload),
        )
    return row["id"]


async def update_publish_result(
    publish_id: int,
    *,
    status: str,
    item_count: int,
    item_count_accepted: int,
    item_count_rejected: int,
    errors: list[dict],
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE published_catalogs
            SET status = $1,
                item_count = $2,
                item_count_accepted = $3,
                item_count_rejected = $4,
                errors = $5::jsonb,
                processed_at = NOW()
            WHERE id = $6
            """,
            status, item_count, item_count_accepted, item_count_rejected,
            json.dumps(errors), publish_id,
        )


# ─── agent_versions ─────────────────────────────────────────────────


async def upsert_agent_version(
    *,
    agent_urn: str,
    version: str,
    bpp_subscriber_id: str,
    beckn_id: str,
    agentfacts_id: Optional[str],
    label: str,
    description: str,
    jurisdiction: Optional[str],
    languages: list[str],
    capability_tags: list[str],
    input_modes: list[str],
    output_modes: list[str],
    pricing_currency: Optional[str],
    pricing_value: Optional[float],
    sla_max_latency_ms: Optional[int],
    agent_facts: dict,
    embedding: list[float],
) -> int:
    """Insert or update the version row and ensure exactly one ``current``
    per agent_urn. Runs as a single transaction so the partial-unique
    constraint cannot momentarily see two current rows.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Flip any existing ``current`` for this urn but different
            # version — even if we are re-publishing the SAME version,
            # this is a no-op (the WHERE excludes our own row).
            await conn.execute(
                """
                UPDATE agent_versions
                SET status = 'deprecated', deprecated_at = NOW()
                WHERE agent_urn = $1 AND version <> $2 AND status = 'current'
                """,
                agent_urn, version,
            )

            row = await conn.fetchrow(
                """
                INSERT INTO agent_versions (
                    agent_urn, version, bpp_subscriber_id, beckn_id, agentfacts_id,
                    label, description, jurisdiction,
                    languages, capability_tags, input_modes, output_modes,
                    pricing_currency, pricing_value, sla_max_latency_ms,
                    agent_facts, embedding, status, published_at, deprecated_at
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11, $12,
                    $13, $14, $15,
                    $16::jsonb, $17, 'current', NOW(), NULL
                )
                ON CONFLICT (agent_urn, version) DO UPDATE SET
                    bpp_subscriber_id = EXCLUDED.bpp_subscriber_id,
                    beckn_id = EXCLUDED.beckn_id,
                    agentfacts_id = EXCLUDED.agentfacts_id,
                    label = EXCLUDED.label,
                    description = EXCLUDED.description,
                    jurisdiction = EXCLUDED.jurisdiction,
                    languages = EXCLUDED.languages,
                    capability_tags = EXCLUDED.capability_tags,
                    input_modes = EXCLUDED.input_modes,
                    output_modes = EXCLUDED.output_modes,
                    pricing_currency = EXCLUDED.pricing_currency,
                    pricing_value = EXCLUDED.pricing_value,
                    sla_max_latency_ms = EXCLUDED.sla_max_latency_ms,
                    agent_facts = EXCLUDED.agent_facts,
                    embedding = EXCLUDED.embedding,
                    status = 'current',
                    published_at = NOW(),
                    deprecated_at = NULL
                RETURNING id
                """,
                agent_urn, version, bpp_subscriber_id, beckn_id, agentfacts_id,
                label, description, jurisdiction,
                languages, capability_tags, input_modes, output_modes,
                pricing_currency, pricing_value, sla_max_latency_ms,
                json.dumps(agent_facts), embedding,
            )
    return row["id"]


async def count_current_agents(bpp_subscriber_id: Optional[str] = None) -> int:
    """For smoke / introspection. Not part of the publish hot path."""
    pool = await get_pool()
    if bpp_subscriber_id is None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS c FROM agent_versions WHERE status='current'"
            )
    else:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS c FROM agent_versions
                WHERE status='current' AND bpp_subscriber_id = $1
                """,
                bpp_subscriber_id,
            )
    return row["c"]
