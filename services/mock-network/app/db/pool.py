"""asyncpg connection pool — singleton, lazy, lifecycle owned by main.py."""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from app.config import load_db_config

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared pool, creating it on first call.

    Tests that exercise repository code in isolation should not call this;
    they should pass their own pool/connection to repository functions.
    The pool returned here is the production-lifecycle one.
    """
    global _pool
    if _pool is None:
        cfg = load_db_config()
        _pool = await asyncpg.create_pool(
            dsn=cfg.dsn,
            min_size=1,
            max_size=10,
            command_timeout=10,
        )
        logger.info("postgres-mocknet pool established (%s@%s:%s/%s)",
                    cfg.user, cfg.host, cfg.port, cfg.name)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("postgres-mocknet pool closed")
