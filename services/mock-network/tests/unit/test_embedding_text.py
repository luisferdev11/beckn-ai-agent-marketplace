"""Tests for ``text_for_agent`` — the prose composer that drives embeddings.

The composition is part of the index's public contract; if it changes,
already-published embeddings drift away from new query embeddings. This
suite locks in the rules.
"""
from __future__ import annotations

from app.embeddings.service import text_for_agent
from tests.factories.payloads import valid_agent_facts


class TestComposition:
    def test_includes_label(self):
        af = valid_agent_facts(label="Magic Summarizer")
        assert "Magic Summarizer" in text_for_agent(af)

    def test_includes_description(self):
        af = valid_agent_facts(description="Handles legal Hindi docs.")
        assert "legal Hindi docs" in text_for_agent(af)

    def test_includes_skill_descriptions(self):
        af = valid_agent_facts()
        af["skills"] = [
            {"id": "x", "description": "Resume contratos",
             "inputModes": ["text"], "outputModes": ["text"]}
        ]
        assert "Resume contratos" in text_for_agent(af)

    def test_includes_jurisdiction(self):
        af = valid_agent_facts(jurisdiction="MEX")
        assert "MEX" in text_for_agent(af)

    def test_omits_pricing(self):
        """Pricing is a filter, not a similarity signal."""
        af = valid_agent_facts()
        af["pricing"] = {"currency": "INR", "value": 99999.99}
        out = text_for_agent(af)
        assert "99999" not in out and "INR" not in out

    def test_handles_missing_optional_fields(self):
        """text_for_agent must not raise on bare-minimum payloads."""
        out = text_for_agent({"label": "A", "description": "B"})
        assert "A" in out and "B" in out


class TestDeterminism:
    def test_same_input_yields_same_output(self):
        af1 = valid_agent_facts()
        af2 = valid_agent_facts()
        assert text_for_agent(af1) == text_for_agent(af2)
