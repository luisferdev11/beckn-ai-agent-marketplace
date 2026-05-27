"""Integration tests for composite ranking in on_discover.

The composite score is verified at three layers:

  1. Each resource in the on_discover envelope MUST carry a numeric
     ``score`` field inside ``resourceAttributes``.

  2. The order of resources within a catalog MUST follow the composite
     score (descending). Ties fall back to similarity.

  3. The order of catalogs MUST follow the maximum composite score
     present in each BPP's bucket — so a BPP whose top agent ranks
     higher appears first.

Uses the in-memory ``fake_discover_index`` extended with optional
``published_at`` and ``bpp_health`` row keys; the fixture computes the
composite score using the same ``app.discover.scoring`` module the
production code path uses, so the test is locked to the formula.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import respx


_BAP_TARGET = "http://bap-marketplace:3001/api/bap-webhook/on_discover"


def _envelope(*, text_search: str = "", bap: str = "bap.example.com") -> dict:
    intent: dict = {}
    if text_search:
        intent["textSearch"] = text_search
    return {
        "context": {
            "networkId": "beckn.one/testnet",
            "action": "discover",
            "version": "2.0.0",
            "bapId": bap,
            "bapUri": "http://onix-bap:8081/bap/receiver",
            "transactionId": str(uuid.uuid4()),
            "messageId": str(uuid.uuid4()),
            "schemaContext": [],
        },
        "message": {"intent": intent},
    }


async def _wait_for_dispatch(route, timeout: float = 2.0, step: float = 0.05) -> bool:
    waited = 0.0
    while waited < timeout:
        if route.called:
            return True
        await asyncio.sleep(step)
        waited += step
    return route.called


def _seed_three_rows_varying_freshness_and_health(fake_discover_index):
    """Three rows with the same similarity (so ordering is driven entirely
    by freshness + health). Each row pins a distinct combination so we
    can reason about the expected order."""
    now = datetime.now(timezone.utc)
    fake_discover_index.rows = [
        {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-stale-but-healthy",
            "label": "Stale yet Healthy",
            "description": "Same similarity, old, healthy.",
            "languages": ["en"], "capability_tags": ["x"],
            "pricing_currency": "INR", "pricing_value": 5.0,
            "sla_max_latency_ms": 5000,
            "agent_facts": {"label": "Stale yet Healthy"},
            "similarity": 0.5,
            "published_at": now - timedelta(days=89),  # near-expiry freshness
            "bpp_health": "healthy",
        },
        {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-fresh-but-unhealthy",
            "label": "Fresh yet Unhealthy",
            "description": "Same similarity, new, unhealthy.",
            "languages": ["en"], "capability_tags": ["x"],
            "pricing_currency": "INR", "pricing_value": 5.0,
            "sla_max_latency_ms": 5000,
            "agent_facts": {"label": "Fresh yet Unhealthy"},
            "similarity": 0.5,
            "published_at": now,  # full freshness
            "bpp_health": "unhealthy",
        },
        {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-fresh-and-healthy",
            "label": "Fresh and Healthy",
            "description": "Same similarity, new, healthy.",
            "languages": ["en"], "capability_tags": ["x"],
            "pricing_currency": "INR", "pricing_value": 5.0,
            "sla_max_latency_ms": 5000,
            "agent_facts": {"label": "Fresh and Healthy"},
            "similarity": 0.5,
            "published_at": now,
            "bpp_health": "healthy",
        },
    ]


class TestScoreIsExposed:
    @respx.mock
    async def test_each_resource_carries_numeric_score(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_three_rows_varying_freshness_and_health(fake_discover_index)
        route = respx.post(_BAP_TARGET).respond(
            200, json={"message": {"ack": {"status": "ACK"}}}
        )
        await client.post("/beckn/discover", json=_envelope(text_search="any"))
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        resources = [r for c in body["message"]["catalogs"] for r in c["resources"]]
        assert resources, "expected at least one resource in the response"
        for res in resources:
            score = res.get("resourceAttributes", {}).get("_marketplaceScore")
            assert isinstance(score, (int, float))
            assert 0.0 <= score <= 1.0

    @respx.mock
    async def test_score_changes_with_health(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_three_rows_varying_freshness_and_health(fake_discover_index)
        route = respx.post(_BAP_TARGET).respond(
            200, json={"message": {"ack": {"status": "ACK"}}}
        )
        await client.post("/beckn/discover", json=_envelope(text_search="any"))
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        by_id = {
            r["id"]: r["resourceAttributes"]["_marketplaceScore"]
            for c in body["message"]["catalogs"] for r in c["resources"]
        }
        # Both have the same similarity + freshness; differing only on health.
        assert by_id["agent-fresh-and-healthy"] > by_id["agent-fresh-but-unhealthy"]


class TestResourcesOrderedByCompositeScore:
    @respx.mock
    async def test_fresh_healthy_ranks_first_when_similarity_ties(
        self, client, fake_subscribers, fake_discover_index
    ):
        _seed_three_rows_varying_freshness_and_health(fake_discover_index)
        route = respx.post(_BAP_TARGET).respond(
            200, json={"message": {"ack": {"status": "ACK"}}}
        )
        await client.post("/beckn/discover", json=_envelope(text_search="any"))
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        # All three rows live under bpp.example.com → single catalog.
        catalog = body["message"]["catalogs"][0]
        ordered_ids = [r["id"] for r in catalog["resources"]]
        # Expected ordering at equal similarity (0.5):
        #   1. fresh + healthy   (max freshness, max health)
        #   2. stale + healthy   (low freshness, max health) — health dominates because
        #                          0.2 * health=1.0 beats 0.2 * freshness=~1.0  +  0.2 * health=0.0
        #   3. fresh + unhealthy (max freshness, min health)
        assert ordered_ids[0] == "agent-fresh-and-healthy"
        assert ordered_ids[-1] == "agent-fresh-but-unhealthy"


class TestCatalogOrderingFollowsBestScorePerBpp:
    @respx.mock
    async def test_bpp_with_higher_top_score_appears_first(
        self, client, fake_subscribers, fake_discover_index
    ):
        now = datetime.now(timezone.utc)
        # BPP-A's best agent: similarity=0.4, fresh, healthy
        # BPP-B's best agent: similarity=0.4, stale, unhealthy → much lower composite
        fake_discover_index.rows = [
            {
                "bpp_subscriber_id": "bpp.example.com",
                "beckn_id": "agent-a-fresh-healthy",
                "label": "A1", "description": "",
                "languages": ["en"], "capability_tags": ["x"],
                "pricing_currency": "INR", "pricing_value": 5.0,
                "sla_max_latency_ms": 5000, "agent_facts": {"label": "A1"},
                "similarity": 0.4,
                "published_at": now,
                "bpp_health": "healthy",
            },
            {
                "bpp_subscriber_id": "bpp-serg.example.com",
                "beckn_id": "agent-b-stale-unhealthy",
                "label": "B1", "description": "",
                "languages": ["en"], "capability_tags": ["x"],
                "pricing_currency": "INR", "pricing_value": 5.0,
                "sla_max_latency_ms": 5000, "agent_facts": {"label": "B1"},
                "similarity": 0.4,
                "published_at": now - timedelta(days=80),
                "bpp_health": "unhealthy",
            },
        ]
        route = respx.post(_BAP_TARGET).respond(
            200, json={"message": {"ack": {"status": "ACK"}}}
        )
        await client.post("/beckn/discover", json=_envelope(text_search="any"))
        await _wait_for_dispatch(route)
        body = json.loads(route.calls.last.request.content)
        provider_ids = [c["provider"]["id"] for c in body["message"]["catalogs"]]
        assert provider_ids[0] == "bpp.example.com"
        assert provider_ids[1] == "bpp-serg.example.com"
