"""Postgres access for the ``subscribers`` table.

Every function acquires its own connection from the shared pool, so callers
(routes, liveness probe) do not need to manage connections. The trade-off
is a small overhead on hot paths — acceptable here because the registry
is not a high-throughput surface.

Tests in ``tests/conftest.py`` monkeypatch every function in this module
with an in-memory fake, so the route layer never sees the real DB during
unit/integration runs. Real DB behaviour is covered by the smoke against
the live container.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from app.db.pool import get_pool


_COLUMNS = """
    id, subscriber_id, role, endpoint_url, backend_health_url, public_key,
    organization, jurisdiction, status, health,
    last_seen_at, consecutive_failures, kyc_data,
    registered_at, updated_at
"""


def _row_to_dict(row) -> dict:
    """asyncpg returns a Record; convert to plain dict and decode JSONB.

    JSONB columns come back as Python strings in some asyncpg setups; we
    decode here so the route layer always sees real dicts.
    """
    d = dict(row)
    for key in ("organization", "kyc_data"):
        val = d.get(key)
        if isinstance(val, str):
            d[key] = json.loads(val) if val else {}
    for key in ("registered_at", "updated_at", "last_seen_at"):
        val = d.get(key)
        if val is not None and not isinstance(val, str):
            d[key] = val.isoformat()
    return d


async def create_subscriber(data: dict) -> dict:
    """Insert a new subscriber. Raises ``asyncpg.UniqueViolationError`` on
    duplicate ``subscriber_id``; the route layer maps that to HTTP 409."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO subscribers
                (subscriber_id, role, endpoint_url, backend_health_url,
                 public_key, organization, jurisdiction)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING {_COLUMNS}
            """,
            data["subscriber_id"],
            data["role"],
            data["endpoint_url"],
            data.get("backend_health_url"),
            data.get("public_key"),
            json.dumps(data.get("organization") or {}),
            data.get("jurisdiction"),
        )
    return _row_to_dict(row)


async def get_subscriber(subscriber_id: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM subscribers WHERE subscriber_id = $1",
            subscriber_id,
        )
    return _row_to_dict(row) if row else None


async def list_subscribers(
    role: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> list[dict]:
    pool = await get_pool()
    clauses: list[str] = []
    params: list = []
    if role is not None:
        params.append(role)
        clauses.append(f"role = ${len(params)}")
    if status_filter is not None:
        params.append(status_filter)
        clauses.append(f"status = ${len(params)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_COLUMNS} FROM subscribers {where} ORDER BY id",
            *params,
        )
    return [_row_to_dict(r) for r in rows]


async def update_subscriber(subscriber_id: str, **fields) -> Optional[dict]:
    """Partial update. Only the listed columns are mutable through this
    function; routes are responsible for filtering out anything else.

    Returns the updated row or ``None`` if the subscriber does not exist.
    """
    mutable = {"status", "organization", "jurisdiction", "kyc_data", "endpoint_url", "public_key", "backend_health_url"}
    updates = {k: v for k, v in fields.items() if k in mutable and v is not None}
    if not updates:
        return await get_subscriber(subscriber_id)

    sets: list[str] = []
    params: list = []
    for key, value in updates.items():
        params.append(json.dumps(value) if key in ("organization", "kyc_data") else value)
        cast = "::jsonb" if key in ("organization", "kyc_data") else ""
        sets.append(f"{key} = ${len(params)}{cast}")
    params.append(subscriber_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE subscribers
            SET {', '.join(sets)}, updated_at = NOW()
            WHERE subscriber_id = ${len(params)}
            RETURNING {_COLUMNS}
            """,
            *params,
        )
    return _row_to_dict(row) if row else None


async def deactivate_subscriber(subscriber_id: str) -> Optional[dict]:
    """Soft-delete: set status='deprecated'. Idempotent."""
    return await update_subscriber(subscriber_id, status="deprecated")


async def update_health(
    subscriber_id: str,
    *,
    health: str,
    last_seen_at: Optional[str],
    consecutive_failures: int,
) -> None:
    """Liveness probe writes only — never read by routes.

    Kept separate from ``update_subscriber`` so the probe path stays
    minimal and cannot accidentally mutate business state.

    ``last_seen_at`` is accepted as an ISO-8601 string for symmetry with
    the rest of the API but converted to ``datetime`` at the SQL
    boundary because asyncpg does not implicitly cast strings into
    timestamptz.
    """
    ts: Optional[datetime] = None
    if last_seen_at:
        ts = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE subscribers
            SET health = $1,
                last_seen_at = $2,
                consecutive_failures = $3,
                updated_at = NOW()
            WHERE subscriber_id = $4
            """,
            health,
            ts,
            consecutive_failures,
            subscriber_id,
        )
