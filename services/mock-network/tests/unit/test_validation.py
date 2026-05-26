"""Unit tests for the AgentFacts validator.

Loads the real schema from ``/app/schemas/agentfacts-v1.json`` (placed
there by the Dockerfile) so we are testing against the actual contract
the route uses in production. No mocks at this layer.
"""
from __future__ import annotations

import pytest

from app.catalog.validation import AgentFactsValidator, ItemError
from tests.factories.payloads import (
    agent_facts_bad_version,
    agent_facts_missing,
    valid_agent_facts,
)


@pytest.fixture(scope="module")
def validator() -> AgentFactsValidator:
    return AgentFactsValidator()


class TestValid:
    def test_well_formed_payload_passes(self, validator):
        assert validator.validate_one("r1", valid_agent_facts()) == []


class TestMissingFields:
    @pytest.mark.parametrize("field", [
        "@context", "@type", "id", "agent_name", "label",
        "description", "version", "provider", "endpoints",
        "capabilities", "skills",
    ])
    def test_missing_required_field_reports_one_error(self, validator, field):
        errors = validator.validate_one("r1", agent_facts_missing(field))
        assert any(field in e.message for e in errors), (
            f"expected error mentioning {field}, got: {[e.message for e in errors]}"
        )

    def test_resource_id_propagates_to_error(self, validator):
        errors = validator.validate_one("agent-zzz", agent_facts_missing("label"))
        assert errors and all(e.resource_id == "agent-zzz" for e in errors)


class TestBadShape:
    def test_non_dict_returns_invalid_type(self, validator):
        errors = validator.validate_one("r1", "not a dict")  # type: ignore[arg-type]
        assert len(errors) == 1
        assert errors[0].code == "INVALID_TYPE"

    def test_version_must_be_semver(self, validator):
        errors = validator.validate_one("r1", agent_facts_bad_version())
        assert any("version" in e.path or "version" in e.message.lower()
                   for e in errors)


class TestErrorShape:
    def test_error_code_is_schema_violation_on_validation_fail(self, validator):
        errors = validator.validate_one("r1", agent_facts_missing("label"))
        assert errors and all(e.code == "SCHEMA_VIOLATION" for e in errors)

    def test_error_includes_jsonpath_when_applicable(self, validator):
        # Force a sub-property violation: invalid version format.
        errors = validator.validate_one("r1", agent_facts_bad_version())
        assert any(e.path.startswith("$.version") for e in errors)
