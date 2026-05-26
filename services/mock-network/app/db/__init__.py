"""Shared asyncpg pool for the mock-network service.

Other submodules (registry, future catalog) reach Postgres only through
``app.db.pool.get_pool``. They do not open their own connections, so we
keep a single point of pool lifecycle.
"""
