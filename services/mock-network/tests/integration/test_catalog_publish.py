"""Integration tests for POST /beckn/catalog/publish.

End-to-end through the FastAPI app: the route runs the real publish
pipeline against the in-memory catalog repository + a deterministic
fake embedder. on_publish delivery (HTTP POST to the BPP backend) is
exercised in a separate test class with respx-style mocking via
monkeypatching ``httpx.AsyncClient``.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.factories.payloads import (
    agent_facts_missing,
    beckn_catalog,
    beckn_resource,
    publish_envelope,
    valid_agent_facts,
)


async def _wait_until(predicate, timeout: float = 2.0, step: float = 0.05) -> bool:
    """Spin until predicate() is truthy or timeout. BackgroundTasks run in
    the event loop after the route returns, so we yield repeatedly to let
    them complete before asserting on side effects.
    """
    waited = 0.0
    while waited < timeout:
        if predicate():
            return True
        await asyncio.sleep(step)
        waited += step
    return predicate()


# ── Synchronous response ───────────────────────────────────────────


class TestPublishSyncResponse:
    async def test_valid_payload_returns_200_ack(self, client):
        resp = await client.post("/beckn/catalog/publish", json=publish_envelope())
        assert resp.status_code == 200
        assert resp.json() == {"message": {"ack": {"status": "ACK"}}}

    async def test_publish_path_is_also_accepted_without_slash_publish(self, client):
        """ONIX routing posts to /beckn/catalog (no /publish suffix)."""
        resp = await client.post("/beckn/catalog", json=publish_envelope())
        assert resp.status_code == 200

    async def test_missing_message_returns_400_nack(self, client):
        env = publish_envelope()
        env.pop("message")
        resp = await client.post("/beckn/catalog/publish", json=env)
        assert resp.status_code == 400
        assert resp.json()["message"]["ack"]["status"] == "NACK"

    async def test_empty_catalogs_returns_400_nack(self, client):
        env = publish_envelope(catalogs=[])
        resp = await client.post("/beckn/catalog/publish", json=env)
        assert resp.status_code == 400


# ── Pipeline side effects ──────────────────────────────────────────


class TestPublishPipeline:
    async def test_valid_resource_lands_in_catalog_store(
        self, client, fake_catalog_store, app
    ):
        await client.post("/beckn/catalog/publish", json=publish_envelope())
        assert await _wait_until(lambda: len(fake_catalog_store["agents"]) == 1)
        assert fake_catalog_store["agents"][0]["status"] == "current"

    async def test_publish_audit_row_is_marked_accepted(
        self, client, fake_catalog_store
    ):
        await client.post("/beckn/catalog/publish", json=publish_envelope())
        await _wait_until(
            lambda: any(p["status"] == "ACCEPTED"
                        for p in fake_catalog_store["publishes"].values())
        )
        publish = next(iter(fake_catalog_store["publishes"].values()))
        assert publish["status"] == "ACCEPTED"
        assert publish["item_count"] == 1
        assert publish["item_count_accepted"] == 1
        assert publish["item_count_rejected"] == 0

    async def test_invalid_resource_is_rejected_status_rejected(
        self, client, fake_catalog_store
    ):
        env = publish_envelope(catalogs=[
            beckn_catalog([beckn_resource(agent_facts_missing("label"))])
        ])
        await client.post("/beckn/catalog/publish", json=env)
        await _wait_until(
            lambda: any(p["status"] in ("REJECTED", "PARTIAL")
                        for p in fake_catalog_store["publishes"].values())
        )
        publish = next(iter(fake_catalog_store["publishes"].values()))
        assert publish["status"] == "REJECTED"
        assert publish["item_count_rejected"] == 1
        assert publish["errors"]  # at least one error captured

    async def test_partial_catalog_marks_partial_and_indexes_valid_only(
        self, client, fake_catalog_store
    ):
        good = beckn_resource(valid_agent_facts(), resource_id="agent-good")
        bad = beckn_resource(agent_facts_missing("label"), resource_id="agent-bad")
        env = publish_envelope(catalogs=[beckn_catalog([good, bad])])
        await client.post("/beckn/catalog/publish", json=env)

        await _wait_until(
            lambda: any(p["status"] == "PARTIAL"
                        for p in fake_catalog_store["publishes"].values())
        )
        publish = next(iter(fake_catalog_store["publishes"].values()))
        assert publish["status"] == "PARTIAL"
        assert publish["item_count_accepted"] == 1
        assert publish["item_count_rejected"] == 1
        assert len(fake_catalog_store["agents"]) == 1
        assert fake_catalog_store["agents"][0]["beckn_id"] == "agent-good"


# ── Versioning ─────────────────────────────────────────────────────


class TestVersioning:
    async def test_new_version_deprecates_previous_current(
        self, client, fake_catalog_store
    ):
        v1 = valid_agent_facts(version="1.0.0")
        await client.post(
            "/beckn/catalog/publish",
            json=publish_envelope(catalogs=[beckn_catalog([beckn_resource(v1)])]),
        )
        await _wait_until(lambda: len(fake_catalog_store["agents"]) == 1)

        v2 = valid_agent_facts(version="1.1.0")
        await client.post(
            "/beckn/catalog/publish",
            json=publish_envelope(catalogs=[beckn_catalog([beckn_resource(v2)])]),
        )
        await _wait_until(lambda: len(fake_catalog_store["agents"]) == 2)

        rows = sorted(fake_catalog_store["agents"], key=lambda r: r["version"])
        assert rows[0]["version"] == "1.0.0"
        assert rows[0]["status"] == "deprecated"
        assert rows[1]["version"] == "1.1.0"
        assert rows[1]["status"] == "current"

    async def test_republishing_same_version_keeps_one_current(
        self, client, fake_catalog_store
    ):
        af = valid_agent_facts()
        for _ in range(3):
            await client.post(
                "/beckn/catalog/publish",
                json=publish_envelope(catalogs=[beckn_catalog([beckn_resource(af)])]),
            )
            await _wait_until(lambda: len(fake_catalog_store["agents"]) >= 1)
        currents = [r for r in fake_catalog_store["agents"] if r["status"] == "current"]
        assert len(currents) == 1
        assert len(fake_catalog_store["agents"]) == 1
