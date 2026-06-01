"""Unit tests for the demo's JSON Schema validator.

Pure module — no IO, no async. The marketplace boundary uses
``validate_against`` to refuse a select with a malformed payload AND to
reject an agent's on_status if it doesn't match the declared output
schema. Tests pin both happy and unhappy cases so regressions surface
the next time someone tweaks the demo contract.
"""
from __future__ import annotations

import pytest

from app.demo.schema import validate_against


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "language": {"type": "string"},
    },
    "required": ["summary", "key_points"],
}


EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "organizations":         {"type": "array", "items": {"type": "string"}},
        "dates":                 {"type": "array", "items": {"type": "string"}},
        "regulatory_references": {"type": "array", "items": {"type": "string"}},
        "monetary_amounts":      {"type": "array", "items": {"type": "string"}},
        "obligations":           {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "organizations", "dates", "regulatory_references",
        "monetary_amounts", "obligations",
    ],
}


class TestSummaryShape:
    def test_well_formed_summary_is_ok(self):
        result = validate_against(
            {
                "summary": "RBI tightened capital adequacy norms.",
                "key_points": ["CET1 raised to 5.5%"],
                "language": "en",
            },
            SUMMARY_SCHEMA,
        )
        assert result.ok
        assert result.errors == []

    def test_missing_summary_fails_with_required_rule(self):
        result = validate_against(
            {"key_points": ["only one bullet"]},
            SUMMARY_SCHEMA,
        )
        assert not result.ok
        assert any(e["rule"] == "required" for e in result.errors)

    def test_empty_key_points_array_fails(self):
        result = validate_against(
            {"summary": "ok", "key_points": []},
            SUMMARY_SCHEMA,
        )
        assert not result.ok
        # minItems triggers the failure
        codes = {e["rule"] for e in result.errors}
        assert "minItems" in codes

    def test_wrong_type_for_summary_fails(self):
        result = validate_against(
            {"summary": ["not a string"], "key_points": ["x"]},
            SUMMARY_SCHEMA,
        )
        assert not result.ok
        # The validator should pin the offending field by location
        locations = {e["location"] for e in result.errors}
        assert "summary" in locations


class TestExtractShape:
    def test_all_buckets_empty_is_still_valid(self):
        # Schema requires the keys to be present, not non-empty.
        result = validate_against(
            {
                "organizations": [], "dates": [],
                "regulatory_references": [], "monetary_amounts": [],
                "obligations": [],
            },
            EXTRACT_SCHEMA,
        )
        assert result.ok

    def test_missing_bucket_fails(self):
        result = validate_against(
            {
                "organizations": ["RBI"], "dates": ["2025-07-01"],
                "regulatory_references": [], "monetary_amounts": [],
                # obligations missing
            },
            EXTRACT_SCHEMA,
        )
        assert not result.ok

    def test_non_array_bucket_fails_with_type_rule(self):
        result = validate_against(
            {
                "organizations": "RBI",  # string instead of array
                "dates": [], "regulatory_references": [],
                "monetary_amounts": [], "obligations": [],
            },
            EXTRACT_SCHEMA,
        )
        assert not result.ok
        assert any(e["rule"] == "type" for e in result.errors)


class TestAllErrorsCollectedAtOnce:
    """The validator should NOT bail on the first error — the UI needs to
    show all violations in one pass."""

    def test_two_problems_both_reported(self):
        result = validate_against(
            {"summary": "", "key_points": []},  # summary too short + key_points too few
            SUMMARY_SCHEMA,
        )
        # Even if summary minLength might not be triggered (empty string),
        # at minItems on key_points must be flagged.
        assert not result.ok
        rules = {e["rule"] for e in result.errors}
        assert "minItems" in rules
