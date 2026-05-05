from __future__ import annotations

import os
import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        password = os.getenv("DB_PASSWORD")
        if not password:
            raise RuntimeError("DB_PASSWORD environment variable is required")
        _pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "beckn_ai_marketplace"),
            user=os.getenv("DB_USER", "postgres"),
            password=password,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
