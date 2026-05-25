"""Unit tests for the filter-to-SQL-params mapping.

We exercise the pure mapping function only; the actual SQL execution is
covered by service-level tests with the in-memory fake. Splitting this
out keeps the SQL bound names locked in and prevents accidental regressions
(e.g. dropping a filter without noticing).
"""
from __future__ import annotations

from app.discover.models import StructuredFilters
from app.discover.query import build_filter_params


class TestBuildFilterParams:
    def test_all_none_for_empty_filters(self):
        params = build_filter_params(StructuredFilters())
        assert all(v is None for v in params.values())

    def test_keys_are_stable(self):
        """The SQL relies on these exact keys; rename = silent breakage."""
        params = build_filter_params(StructuredFilters())
        assert set(params.keys()) == {
            "jurisdiction", "languages", "capabilities",
            "currency", "max_price_value", "max_latency_ms",
        }

    def test_jurisdiction_passes_through(self):
        params = build_filter_params(StructuredFilters(jurisdiction="IN"))
        assert params["jurisdiction"] == "IN"

    def test_languages_normalised_to_list(self):
        params = build_filter_params(StructuredFilters(languages=["hi", "en"]))
        assert params["languages"] == ["hi", "en"]
        assert isinstance(params["languages"], list)

    def test_empty_languages_treated_as_none(self):
        params = build_filter_params(StructuredFilters(languages=[]))
        assert params["languages"] is None

    def test_capabilities_normalised_to_list(self):
        params = build_filter_params(StructuredFilters(capabilities=["a", "b"]))
        assert params["capabilities"] == ["a", "b"]

    def test_empty_capabilities_treated_as_none(self):
        params = build_filter_params(StructuredFilters(capabilities=[]))
        assert params["capabilities"] is None

    def test_currency_passes_through(self):
        params = build_filter_params(StructuredFilters(currency="INR"))
        assert params["currency"] == "INR"

    def test_max_price_value_is_float(self):
        params = build_filter_params(StructuredFilters(max_price_value=12))
        assert params["max_price_value"] == 12.0
        assert isinstance(params["max_price_value"], float)

    def test_max_latency_ms_is_int(self):
        params = build_filter_params(StructuredFilters(max_latency_ms=5000))
        assert params["max_latency_ms"] == 5000
        assert isinstance(params["max_latency_ms"], int)

    def test_zero_max_price_is_preserved_not_none(self):
        """0 is a meaningful constraint (free agents only)."""
        params = build_filter_params(StructuredFilters(max_price_value=0))
        assert params["max_price_value"] == 0.0
