"""Embedding service — sentence-transformers wrapper used by the CDS.

Loaded once per process (model is ~120MB and takes ~2s to initialise).
Tests inject a fake via monkeypatch so they never load the real model.

The wrapper is decoupled from the rest of the catalog code so the
underlying model can be swapped (e.g. switch to bge-m3 multilingual)
without touching anything else.
"""
