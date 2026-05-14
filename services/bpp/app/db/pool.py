from __future__ import annotations

import os
import asyncpg

_catalog_pool: asyncpg.Pool | None = None
_transactions_pool: asyncpg.Pool | None = None


async def _create_pool(db_name: str) -> asyncpg.Pool:
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("DB_PASSWORD environment variable is required")
    return await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=db_name,
        user=os.getenv("DB_USER", "postgres"),
        password=password,
        min_size=2,
        max_size=10,
    )


async def get_pool() -> asyncpg.Pool:
    """Default pool — catalog DB (agents, providers, categories)."""
    return await get_catalog_pool()


async def get_catalog_pool() -> asyncpg.Pool:
    global _catalog_pool
    if _catalog_pool is None:
        _catalog_pool = await _create_pool(
            os.getenv("DB_NAME_CATALOG", "beckn_catalog")
        )
    return _catalog_pool


async def get_transactions_pool() -> asyncpg.Pool:
    global _transactions_pool
    if _transactions_pool is None:
        _transactions_pool = await _create_pool(
            os.getenv("DB_NAME_TRANSACTIONS", "beckn_transactions")
        )
    return _transactions_pool


async def close_pool():
    global _catalog_pool, _transactions_pool
    if _catalog_pool:
        await _catalog_pool.close()
        _catalog_pool = None
    if _transactions_pool:
        await _transactions_pool.close()
        _transactions_pool = None
