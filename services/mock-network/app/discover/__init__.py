"""Discover — semantic + filter retrieval over the indexed catalog.

Replaces the fan-out path that ``services/discovery/`` used to drive.
Implements Beckn v2 ``discover`` / ``on_discover`` over the
``agent_versions`` index populated by Pieza 1's catalog/publish.

Public surface:

  ``app.discover.routes``     FastAPI router mounted at /beckn/discover
  ``app.discover.service``    Orchestration + on_discover dispatch
  ``app.discover.query``      Multi-stage retrieval (filter → rank → score)
  ``app.discover.models``     Pydantic for the request body

Module isolation is the same as elsewhere: routes ↔ service ↔ query;
service additionally reaches into ``registry.repository`` (read-only) to
resolve provider descriptors and into ``embeddings`` for the query
vector. ``query`` is the only file that touches the catalog DB.
"""
