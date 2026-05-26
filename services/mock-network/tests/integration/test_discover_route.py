"""Integration tests for POST /beckn/discover.

Drives the FastAPI app through ASGITransport with:
  - the in-memory ``fake_discover_index`` seeded by each test
  - respx mocking the on_discover delivery to the BAP backend

We assert two contracts:

  Synchronous response:  always 200 + Beckn ACK.
  Asynchronous behaviour: after a brief yield, the on_discover envelope
                          is POSTed to the BAP backend with the catalogs
                          shaped per the spec (one per BPP).
"""
from __future__ import annotations

import asyncio
import json
import uuid

import respx


def _envelope(intent=None, schema_context=None, bap="bap.example.com",
              txn=None) -> dict:
    return {
        "context": {
            "networkId": "beckn.one/testnet",
            "action": "discover",
            "version": "2.0.0",
            "bapId": bap,
            "bapUri": "http://onix-bap:8081/bap/receiver",
            "transactionId": txn or str(uuid.uuid4()),
            "messageId": str(uuid.uuid4()),
            "schemaContext": schema_context or [],
        },
        "message": {"intent": intent or {}},
    }


def _seed_rows(fake_discover_index):
    """Two BPPs, three agents — matches what publish would produce."""
    fake_discover_index.rows = [
        {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-summarizer-001",
            "label": "Legal Document Summarizer",
            "description": "Summarises legal docs in Hindi and English.",
            "jurisdiction": "IND",
            "languages": ["en", "hi"],
            "capability_tags": ["document_summary", "legal_analysis"],
            "pricing_currency": "INR", "pricing_value": 6.0,
            "sla_max_latency_ms": 5000,
            "agent_facts": {"label": "Legal Document Summarizer", "version": "1.0.0"},
            "similarity": 0.7,
        },
        {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-code-reviewer-001",
            "label": "Code Review Assistant",
            "description": "Reviews code for bugs and best practices.",
            "jurisdiction": "IND",
            "languages": ["en"],
            "capability_tags": ["code_review", "security_analysis"],
            "pricing_currency": "INR", "pricing_value": 10.0,
            "sla_max_latency_ms": 30000,
            "agent_facts": {"label": "Code Review Assistant", "version": "1.0.0"},
            "similarity": 0.2,
        },
        {
            "bpp_subscriber_id": "bpp-serg.example.com",
            "beckn_id": "summarizer-v1",
            "label": "Summarizer",
            "description": "Resume textos.",
            "jurisdiction": "MEX",
            "languages": ["es", "en"],
            "capability_tags": ["document_summary"],
            "pricing_currency": "MXN", "pricing_value": 5.0,
            "sla_max_latency_ms": 5000,
            "agent_facts": {"label": "Summarizer", "version": "1.0.0"},
            "similarity": 0.5,
        },
    ]


async def _wait_for_dispatch(route, timeout: float = 2.0, step: float = 0.05) -> bool:
    waited = 0.0
    while waited < timeout:
        if route.called:
            return True
        await asyncio.sleep(step)
        waited += step
    return route.called


# ── Sync response ──────────────────────────────────────────────────


class TestDiscoverSyncResponse:
    async def test_valid_envelope_returns_200_ack(self, client, fake_discover_index):
        resp = await client.post("/beckn/discover", json=_envelope())
        assert resp.status_code == 200
        assert resp.json() == {"message": {"ack": {"status": "ACK"}}}

    async def test_invalid_json_returns_400(self, client):
        resp = await client.post(
            "/beckn/discover",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_non_dict_body_returns_400(self, client):
        resp = await client.post("/beckn/discover", json=["not", "an", "object"])
        assert resp.status_code == 400


# ── Async on_discover dispatch ─────────────────────────────────────


class TestOnDiscoverDispatch:
    @respx.mock
    async def test_callback_is_posted_to_bap_backend(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        await client.post("/beckn/discover", json=_envelope())
        assert await _wait_for_dispatch(route)
        assert route.called

    @respx.mock
    async def test_callback_envelope_is_on_discover_action(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        await client.post("/beckn/discover", json=_envelope())
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        assert body["context"]["action"] == "on_discover"

    @respx.mock
    async def test_callback_contains_one_catalog_per_bpp(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        await client.post("/beckn/discover", json=_envelope())
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        catalogs = body["message"]["catalogs"]
        provider_ids = {c["provider"]["id"] for c in catalogs}
        assert provider_ids == {"bpp.example.com", "bpp-serg.example.com"}

    @respx.mock
    async def test_provider_descriptor_is_filled_from_registry(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        await client.post("/beckn/discover", json=_envelope())
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        for cat in body["message"]["catalogs"]:
            assert cat["provider"]["descriptor"]["name"]  # non-empty

    @respx.mock
    async def test_empty_index_still_delivers_on_discover_with_empty_catalogs(
        self, client, fake_subscribers, fake_discover_index
    ):
        # Don't seed any rows.
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})
        await client.post("/beckn/discover", json=_envelope())
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        assert body["message"]["catalogs"] == []


# ── Filter behaviour ───────────────────────────────────────────────


class TestFiltersHonoured:
    @respx.mock
    async def test_jurisdiction_filter_excludes_other_jurisdictions(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        env = _envelope(intent={"filters": {"jurisdiction": "MEX"}})
        await client.post("/beckn/discover", json=env)
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        all_resources = [r for c in body["message"]["catalogs"] for r in c["resources"]]
        # Only the Serg agent declares MEX.
        assert len(all_resources) == 1
        assert all_resources[0]["id"] == "summarizer-v1"

    @respx.mock
    async def test_languages_filter_keeps_only_supporting_agents(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        env = _envelope(intent={"filters": {"languages": ["hi"]}})
        await client.post("/beckn/discover", json=env)
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        all_resources = [r for c in body["message"]["catalogs"] for r in c["resources"]]
        assert {r["id"] for r in all_resources} == {"agent-summarizer-001"}

    @respx.mock
    async def test_capability_filter(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        env = _envelope(intent={"filters": {"capabilities": ["document_summary"]}})
        await client.post("/beckn/discover", json=env)
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        all_resources = [r for c in body["message"]["catalogs"] for r in c["resources"]]
        assert {r["id"] for r in all_resources} == {
            "agent-summarizer-001", "summarizer-v1",
        }

    @respx.mock
    async def test_max_price_ceiling_excludes_over_budget(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_rows(fake_discover_index)
        target = "http://bap-marketplace:3001/api/bap-webhook/on_discover"
        route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

        env = _envelope(intent={"filters": {"max_price_value": 7.0}})
        await client.post("/beckn/discover", json=env)
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        all_resources = [r for c in body["message"]["catalogs"] for r in c["resources"]]
        # summarizer (INR 6) and serg summarizer (MXN 5) survive; reviewer (INR 10) drops.
        assert {r["id"] for r in all_resources} == {
            "agent-summarizer-001", "summarizer-v1",
        }
