"""Integration tests for the probe HTTP surface (Epic E7)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fake_probe_repo(monkeypatch):
    agents = {
        ("bpp.example.com", "agent-x-001"): {
            "bpp_subscriber_id": "bpp.example.com",
            "beckn_id": "agent-x-001",
            "version": "1.0.0",
            "sla_max_latency_ms": 5000,
            "probe_status": "probation",
            "agent_facts": {
                "inputSchema": {"type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"]},
                "outputSchema": {"type": "object",
                                 "properties": {"summary": {"type": "string"}},
                                 "required": ["summary"]},
            },
        },
    }

    async def _get_agent(bpp, beckn_id):
        a = agents.get((bpp, beckn_id))
        return dict(a) if a else None

    async def _list_probes(bpp, beckn_id, limit=20):
        return [{"id": 1, "passed": True, "probed_at": "2026-06-01T00:00:00Z"}]

    from app.probe import repository
    monkeypatch.setattr(repository, "get_agent", _get_agent)
    monkeypatch.setattr(repository, "list_probes", _list_probes)

    async def _full(agent):
        return {"bpp_subscriber_id": agent["bpp_subscriber_id"],
                "agent_beckn_id": agent["beckn_id"],
                "probe_status": "live", "passed": True,
                "input_valid": True, "output_valid": True,
                "latency_ms": 120, "latency_within_sla": True,
                "failure_reason": None}
    from app.probe import runner
    monkeypatch.setattr(runner, "probe_agent_full", _full)

    yield agents


class TestRetry:
    async def test_retry_unknown_agent_404(self, client):
        resp = await client.post("/api/probes/bpp.example.com/ghost-999/retry")
        assert resp.status_code == 404

    async def test_retry_runs_full_probe(self, client):
        resp = await client.post("/api/probes/bpp.example.com/agent-x-001/retry")
        assert resp.status_code == 200
        body = resp.json()
        assert body["passed"] is True
        assert body["probe_status"] == "live"


class TestHistory:
    async def test_history_returns_probes(self, client):
        resp = await client.get("/api/probes/bpp.example.com/agent-x-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["probe_status"] == "probation"
        assert len(body["probes"]) == 1

    async def test_history_unknown_404(self, client):
        resp = await client.get("/api/probes/bpp.example.com/ghost-999")
        assert resp.status_code == 404
