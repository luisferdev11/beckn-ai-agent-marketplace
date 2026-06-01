"""Unit tests for the dry-run probe path (Epic E, cron mode).

Persistence + status flips are monkeypatched to in-memory captures; the
full Beckn-flow path is covered separately (needs the BAP) and is not
exercised here.
"""
from __future__ import annotations

import pytest

from app.probe import runner


@pytest.fixture
def capture(monkeypatch):
    probes: list[dict] = []
    status: dict[tuple[str, str], str] = {}
    audits: list[dict] = []

    async def _record_probe(**kw):
        probes.append(kw)
        return len(probes)

    async def _set_status(bpp, beckn_id, *, probe_status):
        status[(bpp, beckn_id)] = probe_status

    from app.probe import repository
    monkeypatch.setattr(repository, "record_probe", _record_probe)
    monkeypatch.setattr(repository, "set_probe_status", _set_status)

    async def _audit(**kw):
        audits.append(kw)
    from app.admission import repository as adm_repo
    monkeypatch.setattr(adm_repo, "record_audit", _audit)

    return {"probes": probes, "status": status, "audits": audits}


def _agent(input_schema):
    return {
        "bpp_subscriber_id": "bpp.example.com",
        "beckn_id": "agent-x-001",
        "version": "1.0.0",
        "sla_max_latency_ms": 5000,
        "agent_facts": {"inputSchema": input_schema} if input_schema else {},
    }


class TestDryRun:
    async def test_valid_input_promotes_to_live(self, capture):
        agent = _agent({"type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"]})
        result = await runner.probe_agent_dryrun(agent)
        assert result["passed"] is True
        assert result["probe_status"] == "live"
        assert capture["status"][("bpp.example.com", "agent-x-001")] == "live"
        assert capture["audits"][0]["action"] == "probe_passed"

    async def test_missing_input_schema_fails(self, capture):
        agent = _agent(None)
        result = await runner.probe_agent_dryrun(agent)
        assert result["passed"] is False
        assert result["probe_status"] == "failing_probe"
        assert capture["audits"][0]["action"] == "probe_failed"

    async def test_unsatisfiable_schema_fails(self, capture):
        # A schema requiring a property the synthesiser cannot conjure to
        # satisfy an impossible constraint (min over a string sentinel).
        agent = _agent({"type": "object",
                        "properties": {"n": {"type": "integer", "minimum": 10,
                                             "maximum": 5}},
                        "required": ["n"]})
        result = await runner.probe_agent_dryrun(agent)
        # synth produces 1, which violates minimum:10 → input invalid
        assert result["input_valid"] is False
        assert result["probe_status"] == "failing_probe"

    async def test_dryrun_records_probe_row(self, capture):
        agent = _agent({"type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"]})
        await runner.probe_agent_dryrun(agent)
        assert len(capture["probes"]) == 1
        row = capture["probes"][0]
        assert row["agent_beckn_id"] == "agent-x-001"
        assert row["output_valid"] is None  # dry-run does not execute
        assert row["passed"] is True
