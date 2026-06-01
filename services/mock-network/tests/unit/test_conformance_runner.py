"""Unit tests for the conformance runner — summary maths + status flips.

The kit's HTTP probes are not exercised here (that needs a live BPP and is
covered by the CLI smoke); we test the orchestration: how raw TestResults
become a persisted verdict and how the subscriber status transitions.
"""
from __future__ import annotations

import pytest

from app.conformance import runner
from app.conformance.kit import TestResult


def _results(must_ok: int, must_total: int, should_ok: int, should_total: int):
    out = []
    for i in range(must_total):
        out.append(TestResult(f"must-{i}", "must", i < must_ok))
    for i in range(should_total):
        out.append(TestResult(f"should-{i}", "should", i < should_ok))
    return out


class TestSummarize:
    def test_all_pass(self):
        s = runner._summarize(_results(9, 9, 2, 2), exit_code=0)
        assert s["must_passed"] is True
        assert s["should_passed"] is True
        assert s["total_tests"] == 11
        assert s["passed_tests"] == 11

    def test_one_must_fails(self):
        s = runner._summarize(_results(8, 9, 2, 2), exit_code=1)
        assert s["must_passed"] is False
        assert s["should_passed"] is True

    def test_should_fail_does_not_break_must(self):
        s = runner._summarize(_results(9, 9, 0, 2), exit_code=0)
        assert s["must_passed"] is True
        assert s["should_passed"] is False

    def test_unreachable_is_must_failure(self):
        # exit_code 2 (unreachable) yields no results → must_passed False
        s = runner._summarize([], exit_code=2)
        assert s["must_passed"] is False


class TestRunForSubscriber:
    @pytest.fixture
    def fakes(self, monkeypatch):
        created = []
        finished = []
        audits = []
        status_flips = []

        async def _create_run(subscriber_id):
            created.append(subscriber_id)
            return 42

        async def _finish_run(run_id, **kw):
            finished.append({"run_id": run_id, **kw})

        from app.conformance import repository as conf_repo
        monkeypatch.setattr(conf_repo, "create_run", _create_run)
        monkeypatch.setattr(conf_repo, "finish_run", _finish_run)

        async def _record_audit(**kw):
            audits.append(kw)
        from app.admission import repository as adm_repo
        monkeypatch.setattr(adm_repo, "record_audit", _record_audit)

        return {"created": created, "finished": finished,
                "audits": audits, "status_flips": status_flips}

    async def test_passing_run_persists_and_keeps_pending(
        self, monkeypatch, fakes, fake_subscribers
    ):
        # Seed a pending_admission subscriber in the registry fake store.
        fake_subscribers["bpp-p.example.com"] = {
            **fake_subscribers["bpp.example.com"],
            "subscriber_id": "bpp-p.example.com",
            "status": "pending_admission",
            "backend_health_url": "http://bpp-p:3002",
        }

        async def _fake_run_for_bpp(url, sid, **kw):
            return {"total_tests": 11, "passed_tests": 11, "must_passed": True,
                    "should_passed": True, "results": [], "exit_code": 0}
        monkeypatch.setattr(runner, "run_for_bpp", _fake_run_for_bpp)

        summary = await runner.run_for_subscriber("bpp-p.example.com")
        assert summary["must_passed"] is True
        assert fakes["created"] == ["bpp-p.example.com"]
        assert fakes["finished"][0]["must_passed"] is True
        assert {a["action"] for a in fakes["audits"]} == {"conformance_run"}
        # passing keeps it pending_admission (awaiting admin approval)
        assert fake_subscribers["bpp-p.example.com"]["status"] == "pending_admission"

    async def test_failing_run_parks_failing_conformance(
        self, monkeypatch, fakes, fake_subscribers
    ):
        fake_subscribers["bpp-f.example.com"] = {
            **fake_subscribers["bpp.example.com"],
            "subscriber_id": "bpp-f.example.com",
            "status": "pending_admission",
            "backend_health_url": "http://bpp-f:3002",
        }

        async def _fake_run_for_bpp(url, sid, **kw):
            return {"total_tests": 11, "passed_tests": 6, "must_passed": False,
                    "should_passed": False, "results": [], "exit_code": 1}
        monkeypatch.setattr(runner, "run_for_bpp", _fake_run_for_bpp)

        await runner.run_for_subscriber("bpp-f.example.com")
        assert fake_subscribers["bpp-f.example.com"]["status"] == "failing_conformance"

    async def test_unknown_subscriber_returns_none(self, fakes):
        assert await runner.run_for_subscriber("ghost.example.com") is None

    async def test_no_backend_url_records_failed_run(
        self, monkeypatch, fakes, fake_subscribers
    ):
        fake_subscribers["bpp-nourl.example.com"] = {
            **fake_subscribers["bpp.example.com"],
            "subscriber_id": "bpp-nourl.example.com",
            "status": "pending_admission",
            "backend_health_url": None,
        }
        summary = await runner.run_for_subscriber("bpp-nourl.example.com")
        assert summary["must_passed"] is False
        assert fakes["finished"][0]["must_passed"] is False
        assert fake_subscribers["bpp-nourl.example.com"]["status"] == "failing_conformance"
