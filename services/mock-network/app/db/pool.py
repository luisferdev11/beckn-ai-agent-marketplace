"""asyncpg connection pool — singleton, lazy, lifecycle owned by main.py.

pgvector registration: the ``vector`` column type is not native to
asyncpg. We register the pgvector codec on every new connection via the
pool's ``init`` callback so the catalog repository can pass and read
``list[float]`` transparently.
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import load_db_config

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def _register_codecs(conn: asyncpg.Connection) -> None:
    """Pool ``init`` callback: register pgvector on every connection."""
    await register_vector(conn)


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
            init=_register_codecs,
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
