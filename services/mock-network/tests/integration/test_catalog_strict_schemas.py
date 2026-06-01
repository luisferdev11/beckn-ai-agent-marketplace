"""Integration tests for the strict schema-contract gate on publish (Epic D).

Exercises the publish pipeline directly (``catalog_service.process_publish``)
so we can read the per-item result without waiting on the on_publish
callback. The in-memory ``fake_catalog_store`` (autouse) captures indexed
agents so we can assert ``pipeline_eligible``.
"""
from __future__ import annotations

import pytest

from app import config
from app.catalog import service as catalog_service
from tests.factories.payloads import (
    agent_facts_without_schemas,
    beckn_catalog,
    beckn_resource,
    publish_envelope,
    valid_agent_facts,
)


def _envelope_with(agent_facts, resource_id="agent-x-001"):
    res = beckn_resource(agent_facts, resource_id=resource_id)
    return publish_envelope(catalogs=[beckn_catalog([res])])


class TestStrictMode:
    @pytest.fixture(autouse=True)
    def _force_strict(self, monkeypatch):
        monkeypatch.setenv("STRICT_SCHEMAS", "true")

    async def test_agent_with_schemas_is_accepted(self, fake_catalog_store):
        results = await catalog_service.process_publish(
            _envelope_with(valid_agent_facts())
        )
        assert results[0]["status"] == "ACCEPTED"
        assert results[0]["stats"]["itemCountAccepted"] == 1

    async def test_agent_without_schemas_is_rejected(self, fake_catalog_store):
        results = await catalog_service.process_publish(
            _envelope_with(agent_facts_without_schemas())
        )
        assert results[0]["status"] == "REJECTED"
        codes = [e["code"] for e in results[0]["errors"]]
        assert "MISSING_SCHEMA_CONTRACT" in codes

    async def test_rejection_names_missing_field(self, fake_catalog_store):
        af = valid_agent_facts()
        af.pop("outputSchema")  # only output missing
        results = await catalog_service.process_publish(_envelope_with(af))
        err = next(e for e in results[0]["errors"]
                   if e["code"] == "MISSING_SCHEMA_CONTRACT")
        assert "outputSchema" in err["message"]

    async def test_empty_schema_object_counts_as_missing(self, fake_catalog_store):
        af = valid_agent_facts()
        af["inputSchema"] = {}  # present but empty → still rejected
        results = await catalog_service.process_publish(_envelope_with(af))
        assert results[0]["status"] == "REJECTED"

    async def test_accepted_agent_is_pipeline_eligible(self, fake_catalog_store):
        await catalog_service.process_publish(_envelope_with(valid_agent_facts()))
        agents = fake_catalog_store["agents"]
        assert agents, "agent should have been indexed"
        assert agents[-1]["agent_facts"]["pipeline_eligible"] is True


class TestPermissiveMode:
    @pytest.fixture(autouse=True)
    def _force_permissive(self, monkeypatch):
        monkeypatch.setenv("STRICT_SCHEMAS", "false")

    async def test_agent_without_schemas_is_indexed(self, fake_catalog_store):
        results = await catalog_service.process_publish(
            _envelope_with(agent_facts_without_schemas())
        )
        assert results[0]["status"] == "ACCEPTED"

    async def test_indexed_without_schemas_is_not_pipeline_eligible(
        self, fake_catalog_store
    ):
        await catalog_service.process_publish(
            _envelope_with(agent_facts_without_schemas())
        )
        agents = fake_catalog_store["agents"]
        assert agents[-1]["agent_facts"]["pipeline_eligible"] is False

    async def test_indexed_with_schemas_is_pipeline_eligible(self, fake_catalog_store):
        await catalog_service.process_publish(_envelope_with(valid_agent_facts()))
        agents = fake_catalog_store["agents"]
        assert agents[-1]["agent_facts"]["pipeline_eligible"] is True


def test_config_default_is_strict(monkeypatch):
    monkeypatch.delenv("STRICT_SCHEMAS", raising=False)
    assert config.strict_schemas() is True


def test_config_false_disables_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "false")
    assert config.strict_schemas() is False
