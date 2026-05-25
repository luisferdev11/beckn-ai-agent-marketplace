"""DeDi-compatible identity lookup mock.

ONIX adapters call into this submodule when verifying signatures: given a
subscriber id, return the participant's signing public key, endpoint URL
and role. The response shape matches the real DeDi API at
``fabric.nfh.global/registry/dedi`` exactly except that ``details.url``
points to internal Docker URIs.

This module is intentionally not backed by the Postgres Registry in this
MVP — it holds a static dict so ONIX signature verification cannot break
when the Registry DB is reseeded or unreachable. See the migration
``infra/db/mocknet/migrations/001_schema.sql`` for the rationale.
"""
