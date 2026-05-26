"""Pydantic shapes for the discover request body.

The Beckn v2 ``discover`` envelope carries:

  message.intent.textSearch    free-text query (spec)
  message.intent.filters       per RFC 9535 (JSONPath) — see note below

We additionally accept ``context.schemaContext`` as a list of keywords
for backwards-compat with the BAP today (Pieza 4 will replace this with
proper textSearch from LLM intent extraction).

JSONPath subset: the spec mandates RFC 9535. For MVP we accept a small
structured filter object (``StructuredFilters``) which keeps the
implementation lean while still covering the constraints the briefing's
stories need (jurisdiction, languages, capabilities, price, SLA).
Adopting full JSONPath is tracked as a follow-up.

Empty or omitted fields mean "no constraint". An empty intent returns
every ``current`` agent (helpful for the demo + dev).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StructuredFilters(BaseModel):
    """The MVP shape we accept under ``intent.filters``.

    Field semantics:

      jurisdiction       Exact match on ``agent_versions.jurisdiction``.
      languages          ALL of these must be in ``agent_versions.languages``.
      capabilities       ALL of these must be in ``agent_versions.capability_tags``.
      currency           Exact match on ``agent_versions.pricing_currency``.
      max_price_value    Ceiling on ``agent_versions.pricing_value``.
      max_latency_ms     Ceiling on ``agent_versions.sla_max_latency_ms``.
    """
    model_config = ConfigDict(extra="ignore")

    jurisdiction: Optional[str] = None
    languages: Optional[list[str]] = None
    capabilities: Optional[list[str]] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    max_price_value: Optional[float] = None
    max_latency_ms: Optional[int] = None


class DiscoverQuery(BaseModel):
    """Normalised query the route layer hands to the retrieval pipeline.

    Constructed by ``from_envelope`` so route code never deals with the
    polymorphism of the Beckn envelope (schemaContext list vs textSearch
    string).
    """
    model_config = ConfigDict(extra="ignore")

    text_search: str = ""
    filters: StructuredFilters = Field(default_factory=StructuredFilters)
    limit: int = Field(default=20, ge=1, le=100)


def from_envelope(envelope: dict) -> DiscoverQuery:
    """Parse the inbound Beckn envelope into a DiscoverQuery.

    Precedence for text:
      1. ``message.intent.textSearch`` if present and non-empty (spec)
      2. ``context.schemaContext`` joined by spaces (BAP backwards-compat)
      3. Empty (returns most-recent agents)
    """
    context = envelope.get("context") or {}
    intent = (envelope.get("message") or {}).get("intent") or {}

    text_search = (intent.get("textSearch") or "").strip()
    if not text_search:
        keywords = context.get("schemaContext") or []
        if isinstance(keywords, list):
            text_search = " ".join(k for k in keywords if isinstance(k, str)).strip()

    raw_filters = intent.get("filters") or {}
    if not isinstance(raw_filters, dict):
        raw_filters = {}
    filters = StructuredFilters.model_validate(raw_filters)

    limit_raw = intent.get("limit")
    limit = 20
    if isinstance(limit_raw, int) and 1 <= limit_raw <= 100:
        limit = limit_raw

    return DiscoverQuery(text_search=text_search, filters=filters, limit=limit)
