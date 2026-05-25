"""EmbeddingService — semantic vector generator backed by sentence-transformers.

The default model is ``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2``
which produces 384-dimensional vectors and supports >50 languages including
Hindi, Spanish and English. That language coverage matters because the
briefing's primary market is India with Hindi+English content; an English-only
encoder would degrade recall sharply for Hindi-language tasks.

Two public functions:

  embed(text)                  Embed an arbitrary text query (used by discover).

  text_for_agent(agent_facts)  Compose the prose we want to index for an
                               agent. Stable composition so we never embed
                               different fields between publish and discover.

  embed_agent(agent_facts)     Convenience: text_for_agent then embed.

The composition deliberately leaves out fields like ``pricing`` and
``sla.maxLatencyMs`` because those should drive *filtering*, not *ranking*.
A 4 INR agent and a 4000 INR agent are equally relevant to "summarise this
legal doc" — the price is a constraint, not a similarity signal.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class EmbeddingService:
    """Lazy-loading wrapper. The model is pulled into memory on the first
    embed() call; subsequent calls reuse it. Lazy because the catalog
    routes import this module at startup but we want the test suite to
    avoid the model load entirely (via monkeypatch)."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        # Imported here, not at module top, so importing this file in tests
        # does not transitively pull in sentence_transformers.
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("embeddings: loading model %s", self.model_name)
        self._model = SentenceTransformer(self.model_name)
        logger.info("embeddings: model ready (%d-dim)", EMBEDDING_DIM)

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * EMBEDDING_DIM
        self._ensure_loaded()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()


_default_service: Optional[EmbeddingService] = None


def get_default_service() -> EmbeddingService:
    """Module-level singleton — keeps the model in memory across requests."""
    global _default_service
    if _default_service is None:
        _default_service = EmbeddingService()
    return _default_service


def text_for_agent(agent_facts: dict) -> str:
    """Compose the indexable prose for one agent.

    Stable order matters: changing this means the published embeddings
    drift away from new query embeddings until every agent is re-published.
    Treat this function as part of the public contract of the index.
    """
    parts: list[str] = []

    label = agent_facts.get("label") or ""
    if label:
        parts.append(label)

    desc = agent_facts.get("description") or ""
    if desc:
        parts.append(desc)

    skills = agent_facts.get("skills") or []
    for skill in skills if isinstance(skills, list) else []:
        sd = skill.get("description") if isinstance(skill, dict) else None
        if sd:
            parts.append(sd)

    caps = agent_facts.get("capabilities") or {}
    if isinstance(caps, dict):
        modalities = caps.get("modalities") or []
        if isinstance(modalities, list) and modalities:
            parts.append("modalities: " + ", ".join(str(m) for m in modalities))

    jurisdiction = agent_facts.get("jurisdiction")
    if jurisdiction:
        parts.append(f"jurisdiction: {jurisdiction}")

    return ". ".join(p.strip() for p in parts if p.strip())


def embed_agent(agent_facts: dict, service: Optional[EmbeddingService] = None) -> list[float]:
    service = service or get_default_service()
    return service.embed(text_for_agent(agent_facts))
