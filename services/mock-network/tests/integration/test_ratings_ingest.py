"""Integration tests for POST /cds/ratings/ingest.

Contract:

  - Valid body → 200 with the updated aggregate (count + avg).
  - Repeated ingests for the same agent accumulate into a rolling average.
  - Missing required fields → 422.
  - Score outside [scoreMin, scoreMax] → 422.
  - GET /cds/ratings/aggregate returns the current snapshot.
"""
from __future__ import annotations

import pytest


def _payload(*, bpp="bpp.example.com", agent="agent-summarizer-001",
             score=4.5, min_=1.0, max_=5.0) -> dict:
    return {
        "bppSubscriberId": bpp,
        "agentBecknId":    agent,
        "score":           score,
        "scoreMin":        min_,
        "scoreMax":        max_,
    }


class TestIngestHappyPath:
    async def test_first_ingest_returns_count_1(self, client):
        resp = await client.post("/cds/ratings/ingest", json=_payload(score=4.0))
        assert resp.status_code == 200
        agg = resp.json()["aggregate"]
        assert agg["ratingCount"] == 1
        assert agg["avgScore"] == pytest.approx(4.0)

    async def test_subsequent_ingests_accumulate(self, client):
        await client.post("/cds/ratings/ingest", json=_payload(score=4.0))
        await client.post("/cds/ratings/ingest", json=_payload(score=5.0))
        resp = await client.post("/cds/ratings/ingest", json=_payload(score=3.0))
        agg = resp.json()["aggregate"]
        assert agg["ratingCount"] == 3
        assert agg["avgScore"] == pytest.approx(4.0)  # (4+5+3)/3

    async def test_different_agents_are_independent(self, client):
        await client.post("/cds/ratings/ingest",
                          json=_payload(agent="agent-a", score=5.0))
        await client.post("/cds/ratings/ingest",
                          json=_payload(agent="agent-b", score=1.0))
        a = await client.get(
            "/cds/ratings/aggregate",
            params={"bppSubscriberId": "bpp.example.com", "agentBecknId": "agent-a"},
        )
        b = await client.get(
            "/cds/ratings/aggregate",
            params={"bppSubscriberId": "bpp.example.com", "agentBecknId": "agent-b"},
        )
        assert a.json()["avgScore"] == pytest.approx(5.0)
        assert b.json()["avgScore"] == pytest.approx(1.0)


class TestIngestValidation:
    async def test_missing_score_returns_422(self, client):
        body = _payload()
        body.pop("score")
        resp = await client.post("/cds/ratings/ingest", json=body)
        assert resp.status_code == 422

    async def test_empty_bpp_returns_422(self, client):
        resp = await client.post("/cds/ratings/ingest", json=_payload(bpp=""))
        assert resp.status_code == 422

    async def test_empty_agent_returns_422(self, client):
        resp = await client.post("/cds/ratings/ingest", json=_payload(agent=""))
        assert resp.status_code == 422

    async def test_score_below_minimum_returns_422(self, client):
        resp = await client.post(
            "/cds/ratings/ingest", json=_payload(score=0.5)
        )
        assert resp.status_code == 422

    async def test_score_above_maximum_returns_422(self, client):
        resp = await client.post(
            "/cds/ratings/ingest", json=_payload(score=42.0)
        )
        assert resp.status_code == 422

    async def test_min_not_strictly_less_than_max_returns_422(self, client):
        resp = await client.post(
            "/cds/ratings/ingest",
            json=_payload(min_=5.0, max_=5.0, score=5.0),
        )
        assert resp.status_code == 422


class TestAggregateRead:
    async def test_unknown_agent_returns_zero(self, client):
        resp = await client.get(
            "/cds/ratings/aggregate",
            params={"bppSubscriberId": "bpp.unknown", "agentBecknId": "agent-X"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ratingCount"] == 0
        assert body["avgScore"] == 0.0
