"""Postgres access for the agent probe (``agent_probes`` + the
``agent_versions.probe_status`` / ``last_probe_at`` lifecycle columns)."""
from __future__ import annotations

import json
from typing import Optional

from app.db.pool import get_pool


def _decode_facts(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


async def get_agent(bpp_subscriber_id: str, beckn_id: str) -> Optional[dict]:
    """Fetch the current version of one agent for probing."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT bpp_subscriber_id, beckn_id, version, label,
                   sla_max_latency_ms, agent_facts, probe_status
            FROM agent_versions
            WHERE bpp_subscriber_id = $1 AND beckn_id = $2 AND status = 'current'
            """,
            bpp_subscriber_id,
            beckn_id,
        )
    if not row:
        return None
    d = dict(row)
    d["agent_facts"] = _decode_facts(d.get("agent_facts"))
    return d


async def list_probation_agents(limit: int = 100) -> list[dict]:
    """Agents awaiting their first (or a retried) probe. Joined against the
    Registry so the probe can skip agents whose BPP is not active."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT av.bpp_subscriber_id, av.beckn_id, av.version, av.label,
                   av.sla_max_latency_ms, av.agent_facts
            FROM agent_versions av
            JOIN subscribers s ON s.subscriber_id = av.bpp_subscriber_id
            WHERE av.status = 'current'
              AND av.probe_status = 'probation'
              AND s.status = 'active'
            ORDER BY av.published_at ASC
            LIMIT $1
            """,
            limit,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["agent_facts"] = _decode_facts(d.get("agent_facts"))
        out.append(d)
    return out


async def record_probe(
    *,
    bpp_subscriber_id: str,
    agent_beckn_id: str,
    agent_version: str,
    input_payload: Optional[dict],
    output_payload: Optional[dict],
    input_valid: Optional[bool],
    output_valid: Optional[bool],
    latency_ms: Optional[int],
    latency_within_sla: Optional[bool],
    passed: bool,
    failure_reason: Optional[str],
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agent_probes
                (bpp_subscriber_id, agent_beckn_id, agent_version,
                 input_payload, output_payload, input_valid, output_valid,
                 latency_ms, latency_within_sla, passed, failure_reason)
            VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7,$8,$9,$10,$11)
            RETURNING id
            """,
            bpp_subscriber_id,
            agent_beckn_id,
            agent_version,
            json.dumps(input_payload) if input_payload is not None else None,
            json.dumps(output_payload) if output_payload is not None else None,
            input_valid,
            output_valid,
            latency_ms,
            latency_within_sla,
            passed,
            failure_reason,
        )
    return int(row["id"])


async def set_probe_status(
    bpp_subscriber_id: str, beckn_id: str, *, probe_status: str,
) -> None:
    """Update the agent's lifecycle status + last_probe_at timestamp."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE agent_versions
            SET probe_status = $3, last_probe_at = NOW()
            WHERE bpp_subscriber_id = $1 AND beckn_id = $2 AND status = 'current'
            """,
            bpp_subscriber_id,
            beckn_id,
            probe_status,
        )


async def list_probes(bpp_subscriber_id: str, beckn_id: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, agent_version, probed_at, input_valid, output_valid,
                   latency_ms, latency_within_sla, passed, failure_reason
            FROM agent_probes
            WHERE bpp_subscriber_id = $1 AND agent_beckn_id = $2
            ORDER BY probed_at DESC
            LIMIT $3
            """,
            bpp_subscriber_id,
            beckn_id,
            limit,
        )
    out = []
    for r in rows:
        d = dict(r)
        if d.get("probed_at") is not None and not isinstance(d["probed_at"], str):
            d["probed_at"] = d["probed_at"].isoformat()
        out.append(d)
    return out
