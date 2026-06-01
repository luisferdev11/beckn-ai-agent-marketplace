"""Postgres access for ``admission_requests``, ``subscriber_audit`` and
read access to ``conformance_runs`` (for the approval gate + admin detail).

Mirrors the conventions of ``app.registry.repository``: each function
acquires its own connection from the shared pool, JSONB columns are
decoded to dicts, and timestamps are returned as ISO strings. Tests
monkeypatch every function with an in-memory fake.
"""
from __future__ import annotations

import json
from typing import Optional

from app.db.pool import get_pool

_ADMISSION_COLUMNS = """
    id, subscriber_id, submitted_by_email, organization_data,
    requested_at, reviewed_at, reviewed_by, decision, decision_reason
"""


def _decode(row, *, json_keys: tuple[str, ...], ts_keys: tuple[str, ...]) -> dict:
    d = dict(row)
    for key in json_keys:
        val = d.get(key)
        if isinstance(val, str):
            d[key] = json.loads(val) if val else {}
    for key in ts_keys:
        val = d.get(key)
        if val is not None and not isinstance(val, str):
            d[key] = val.isoformat()
    return d


def _admission_to_dict(row) -> dict:
    return _decode(
        row,
        json_keys=("organization_data",),
        ts_keys=("requested_at", "reviewed_at"),
    )


# ─── admission_requests ─────────────────────────────────────────────


async def create_request(
    *,
    subscriber_id: str,
    submitted_by_email: Optional[str],
    organization_data: dict,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO admission_requests
                (subscriber_id, submitted_by_email, organization_data)
            VALUES ($1, $2, $3::jsonb)
            RETURNING {_ADMISSION_COLUMNS}
            """,
            subscriber_id,
            submitted_by_email,
            json.dumps(organization_data or {}),
        )
    return _admission_to_dict(row)


async def get_request(request_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_ADMISSION_COLUMNS} FROM admission_requests WHERE id = $1",
            request_id,
        )
    return _admission_to_dict(row) if row else None


async def list_requests(decision: Optional[str] = None) -> list[dict]:
    pool = await get_pool()
    clause = ""
    params: list = []
    if decision is not None:
        params.append(decision)
        clause = "WHERE decision = $1"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_ADMISSION_COLUMNS} FROM admission_requests "
            f"{clause} ORDER BY requested_at DESC",
            *params,
        )
    return [_admission_to_dict(r) for r in rows]


async def set_decision(
    request_id: int,
    *,
    decision: str,
    reviewed_by: Optional[str],
    decision_reason: Optional[str],
) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE admission_requests
            SET decision = $2,
                reviewed_by = $3,
                decision_reason = $4,
                reviewed_at = NOW()
            WHERE id = $1
            RETURNING {_ADMISSION_COLUMNS}
            """,
            request_id,
            decision,
            reviewed_by,
            decision_reason,
        )
    return _admission_to_dict(row) if row else None


# ─── subscriber_audit ───────────────────────────────────────────────


async def record_audit(
    *,
    subscriber_id: str,
    action: str,
    actor: str = "system",
    details: Optional[dict] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subscriber_audit (subscriber_id, action, actor, details)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            subscriber_id,
            action,
            actor,
            json.dumps(details or {}),
        )


async def list_audit(subscriber_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, subscriber_id, action, actor, details, occurred_at
            FROM subscriber_audit
            WHERE subscriber_id = $1
            ORDER BY occurred_at DESC
            """,
            subscriber_id,
        )
    return [
        _decode(r, json_keys=("details",), ts_keys=("occurred_at",))
        for r in rows
    ]


# ─── conformance_runs (read for the approval gate + admin detail) ───


async def latest_conformance_run(subscriber_id: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, subscriber_id, started_at, finished_at, total_tests,
                   passed_tests, must_passed, should_passed, results
            FROM conformance_runs
            WHERE subscriber_id = $1
            ORDER BY started_at DESC
            LIMIT 1
            """,
            subscriber_id,
        )
    if not row:
        return None
    return _decode(row, json_keys=("results",), ts_keys=("started_at", "finished_at"))
