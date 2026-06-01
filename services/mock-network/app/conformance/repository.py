"""Postgres access for ``conformance_runs``.

A run is recorded in two steps: ``create_run`` inserts the started row so
an in-flight run is visible, then ``finish_run`` writes the aggregate
verdict + per-test detail once the kit completes.
"""
from __future__ import annotations

import json
from typing import Optional

from app.db.pool import get_pool


async def create_run(subscriber_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO conformance_runs (subscriber_id)
            VALUES ($1)
            RETURNING id
            """,
            subscriber_id,
        )
    return int(row["id"])


async def finish_run(
    run_id: int,
    *,
    total_tests: int,
    passed_tests: int,
    must_passed: bool,
    should_passed: bool,
    results: list[dict],
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE conformance_runs
            SET finished_at = NOW(),
                total_tests = $2,
                passed_tests = $3,
                must_passed = $4,
                should_passed = $5,
                results = $6::jsonb
            WHERE id = $1
            """,
            run_id,
            total_tests,
            passed_tests,
            must_passed,
            should_passed,
            json.dumps(results),
        )


async def get_run(run_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, subscriber_id, started_at, finished_at, total_tests,
                   passed_tests, must_passed, should_passed, results
            FROM conformance_runs WHERE id = $1
            """,
            run_id,
        )
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("results"), str):
        d["results"] = json.loads(d["results"])
    for k in ("started_at", "finished_at"):
        if d.get(k) is not None and not isinstance(d[k], str):
            d[k] = d[k].isoformat()
    return d
