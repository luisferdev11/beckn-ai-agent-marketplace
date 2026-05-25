"""Unit tests for the DiscoverQuery envelope parsing.

Lock in the contract that:
  - text_search comes from intent.textSearch first, else schemaContext
  - filters parse from intent.filters into StructuredFilters
  - missing/empty intent yields an empty query (returns all current)
  - unknown filter fields are ignored (not rejected)
"""
from __future__ import annotations

from app.discover.models import DiscoverQuery, StructuredFilters, from_envelope


def _envelope(intent=None, schema_context=None) -> dict:
    return {
        "context": {
            "transactionId": "t1",
            "schemaContext": schema_context if schema_context is not None else [],
        },
        "message": {"intent": intent or {}},
    }


class TestTextSearchPrecedence:
    def test_intent_text_search_takes_precedence(self):
        env = _envelope(
            intent={"textSearch": "summarize legal docs"},
            schema_context=["banking", "regulatory"],
        )
        q = from_envelope(env)
        assert q.text_search == "summarize legal docs"

    def test_falls_back_to_schema_context_when_text_search_empty(self):
        env = _envelope(
            intent={"textSearch": ""},
            schema_context=["banking", "regulatory"],
        )
        q = from_envelope(env)
        assert "banking" in q.text_search and "regulatory" in q.text_search

    def test_no_text_anywhere_yields_empty_string(self):
        env = _envelope()
        q = from_envelope(env)
        assert q.text_search == ""

    def test_schema_context_strings_are_joined(self):
        env = _envelope(schema_context=["legal", "docs", "hindi"])
        q = from_envelope(env)
        assert q.text_search == "legal docs hindi"

    def test_non_string_keywords_are_skipped(self):
        env = _envelope(schema_context=["legal", 123, None, "docs"])
        q = from_envelope(env)
        assert q.text_search == "legal docs"


class TestFiltersParsing:
    def test_jurisdiction_filter(self):
        env = _envelope(intent={"filters": {"jurisdiction": "IN"}})
        q = from_envelope(env)
        assert q.filters.jurisdiction == "IN"

    def test_languages_filter(self):
        env = _envelope(intent={"filters": {"languages": ["hi", "en"]}})
        q = from_envelope(env)
        assert q.filters.languages == ["hi", "en"]

    def test_capabilities_filter(self):
        env = _envelope(intent={"filters": {"capabilities": ["document_summary"]}})
        q = from_envelope(env)
        assert q.filters.capabilities == ["document_summary"]

    def test_pricing_filters(self):
        env = _envelope(intent={"filters": {"currency": "INR", "max_price_value": 12.5}})
        q = from_envelope(env)
        assert q.filters.currency == "INR"
        assert q.filters.max_price_value == 12.5

    def test_sla_filter(self):
        env = _envelope(intent={"filters": {"max_latency_ms": 5000}})
        q = from_envelope(env)
        assert q.filters.max_latency_ms == 5000

    def test_no_filters_yields_empty_filter_object(self):
        q = from_envelope(_envelope())
        assert q.filters == StructuredFilters()

    def test_unknown_filter_keys_are_ignored(self):
        env = _envelope(intent={"filters": {"jurisdiction": "IN", "totally_unknown": "x"}})
        q = from_envelope(env)
        assert q.filters.jurisdiction == "IN"

    def test_non_dict_filters_is_treated_as_empty(self):
        env = _envelope(intent={"filters": "not a dict"})  # type: ignore[dict-item]
        q = from_envelope(env)
        assert q.filters == StructuredFilters()

    def test_currency_must_be_three_chars(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StructuredFilters(currency="INRR")


class TestLimit:
    def test_default_limit_is_20(self):
        q = from_envelope(_envelope())
        assert q.limit == 20

    def test_intent_limit_is_honoured(self):
        env = _envelope(intent={"limit": 5})
        q = from_envelope(env)
        assert q.limit == 5

    def test_intent_limit_out_of_range_falls_back_to_default(self):
        env = _envelope(intent={"limit": 999})
        q = from_envelope(env)
        assert q.limit == 20
