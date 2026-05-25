"""Registry — BAP/BPP onboarding metadata + liveness state.

Postgres-backed CRUD over the ``subscribers`` table. Owned exclusively
by this submodule; no other code touches the table directly.

Public surface:

  - ``app.registry.routes``     FastAPI router mounted at /registry
  - ``app.registry.liveness``   APScheduler probe that updates
                                 ``last_seen_at`` and ``health``

Repository functions live in ``app.registry.repository`` and accept an
asyncpg pool argument so they remain unit-testable without spinning up
the global pool.
"""
