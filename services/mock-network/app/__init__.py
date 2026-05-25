"""Mock Beckn Network service package.

Hosts three logically independent surfaces:

  - ``app.dedi``      DeDi-compatible signature/identity lookup. Hardcoded
                      data so ONIX signature verification keeps working
                      without a live network.
  - ``app.registry``  Postgres-backed BPP/BAP/CDS onboarding metadata.
                      Source of truth for status, liveness, KYC,
                      organisation profile. Pieza 3 of the discover v2
                      roadmap.
  - ``app.catalog``   (Pieza 1, not yet) Catalog publish + index.

Each surface owns its own routes and storage; they share only the
asyncpg pool exposed by ``app.db.pool``.
"""
