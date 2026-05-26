"""Catalog Discovery Service surface — placeholder until Pieza 1.

Currently exposes a stub that ACKs any catalog/publish payload without
persisting. Pieza 1 will replace this with a Postgres-backed index that
validates each item against the AgentFacts schema, computes embeddings
and emits the async ``on_publish`` callback to the originating BPP.
"""
