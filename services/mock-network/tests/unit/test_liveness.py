"""Unit tests for the liveness probe logic.

Network I/O is replaced by a ``FakeProber`` that returns canned results,
so we exercise the policy (when to mark healthy/degraded/down, how
consecutive_failures evolves, which subscribers are skipped) without
opening real sockets.

The repository is the same in-memory fake used by route tests, so
assertions about persisted state simply read back from the
``fake_subscribers`` dict.
"""
from __future__ import annotations

from typing import Optional

import pytest

from app.registry import liveness


class FakeProber:
    """Returns the same fixed result for every probe call.

    Records every URL it was asked about so assertions can verify the
    derived probe URL (not the raw endpoint_url).
    """

    def __init__(self, health: str, latency_ms: int = 50):
        self.result = (health, latency_ms)
        self.calls: list[str] = []

    async def probe(self, base_url: str) -> tuple[str, int]:
        self.calls.append(base_url)
        return self.result


def _subscriber(
    sid: str = "bpp.example.com",
    status: str = "active",
    consecutive_failures: int = 0,
    last_seen_at: Optional[str] = None,
    endpoint_url: str = "http://onix-bpp:8082/bpp/receiver",
) -> dict:
    return {
        "subscriber_id": sid,
        "role": "BPP",
        "endpoint_url": endpoint_url,
        "status": status,
        "consecutive_failures": consecutive_failures,
        "last_seen_at": last_seen_at,
    }


# ── probe URL derivation ─────────────────────────────────────────────


class TestDeriveProbeUrl:
    def test_prefers_backend_health_url_when_set(self):
        s = _subscriber(endpoint_url="http://onix-bpp:8082/bpp/receiver")
        s["backend_health_url"] = "http://bpp-provider:3002"
        assert liveness._derive_probe_url(s) == "http://bpp-provider:3002"

    def test_strips_bap_receiver_suffix_when_no_backend_url(self):
        s = _subscriber(endpoint_url="http://onix-bap:8081/bap/receiver")
        assert liveness._derive_probe_url(s) == "http://onix-bap:8081"

    def test_strips_bpp_receiver_suffix_when_no_backend_url(self):
        s = _subscriber(endpoint_url="http://onix-bpp:8082/bpp/receiver")
        assert liveness._derive_probe_url(s) == "http://onix-bpp:8082"

    def test_unknown_suffix_falls_back_to_raw(self):
        s = _subscriber(endpoint_url="http://something/else")
        assert liveness._derive_probe_url(s) == "http://something/else"


# ── probe_subscriber: status gating ──────────────────────────────────


class TestProbeStatusGating:
    async def test_deprecated_subscriber_is_skipped(self, fake_subscribers):
        s = _subscriber(status="deprecated")
        prober = FakeProber("healthy")
        await liveness.probe_subscriber(s, prober)
        assert prober.calls == []  # no probe issued

    async def test_pending_kyc_subscriber_is_skipped(self, fake_subscribers):
        s = _subscriber(status="pending_kyc")
        prober = FakeProber("healthy")
        await liveness.probe_subscriber(s, prober)
        assert prober.calls == []

    async def test_active_subscriber_is_probed(self, fake_subscribers):
        s = _subscriber(status="active")
        prober = FakeProber("healthy")
        await liveness.probe_subscriber(s, prober)
        assert len(prober.calls) == 1

    async def test_suspended_subscriber_is_still_probed(self, fake_subscribers):
        """Admins need to see if a suspended subscriber recovers."""
        s = _subscriber(status="suspended")
        prober = FakeProber("healthy")
        await liveness.probe_subscriber(s, prober)
        assert len(prober.calls) == 1


# ── probe_subscriber: state transitions ──────────────────────────────


class TestProbeStateTransitions:
    async def test_healthy_probe_persists_healthy(self, fake_subscribers):
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com"), FakeProber("healthy")
        )
        stored = fake_subscribers["bpp.example.com"]
        assert stored["health"] == "healthy"

    async def test_healthy_probe_updates_last_seen_at(self, fake_subscribers):
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com", last_seen_at=None),
            FakeProber("healthy"),
        )
        stored = fake_subscribers["bpp.example.com"]
        assert stored["last_seen_at"] is not None

    async def test_healthy_probe_resets_failures(self, fake_subscribers):
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com", consecutive_failures=5),
            FakeProber("healthy"),
        )
        assert fake_subscribers["bpp.example.com"]["consecutive_failures"] == 0

    async def test_degraded_probe_persists_degraded(self, fake_subscribers):
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com"), FakeProber("degraded")
        )
        assert fake_subscribers["bpp.example.com"]["health"] == "degraded"

    async def test_degraded_probe_also_resets_failures(self, fake_subscribers):
        """Reachable means alive, even if slow or 5xx."""
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com", consecutive_failures=3),
            FakeProber("degraded"),
        )
        assert fake_subscribers["bpp.example.com"]["consecutive_failures"] == 0

    async def test_down_probe_increments_failures(self, fake_subscribers):
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com", consecutive_failures=2),
            FakeProber("down"),
        )
        assert fake_subscribers["bpp.example.com"]["consecutive_failures"] == 3

    async def test_down_probe_does_not_touch_last_seen_at(self, fake_subscribers):
        previous = "2026-05-22T10:00:00+00:00"
        # Seed an existing last_seen_at on the stored row before probing.
        fake_subscribers["bpp.example.com"]["last_seen_at"] = previous
        await liveness.probe_subscriber(
            _subscriber("bpp.example.com", last_seen_at=previous),
            FakeProber("down"),
        )
        assert fake_subscribers["bpp.example.com"]["last_seen_at"] == previous


# ── probe_all: fan-out ───────────────────────────────────────────────


class TestProbeAll:
    async def test_probes_every_active_subscriber(self, fake_subscribers):
        prober = FakeProber("healthy")
        await liveness.probe_all(prober=prober)
        # The three seeded identities are all active.
        assert len(prober.calls) == 3

    async def test_skips_deprecated_subscribers(self, fake_subscribers):
        fake_subscribers["bpp.example.com"]["status"] = "deprecated"
        prober = FakeProber("healthy")
        await liveness.probe_all(prober=prober)
        assert len(prober.calls) == 2

    async def test_one_subscriber_crashing_does_not_block_others(self, fake_subscribers):
        """A crashing probe must not raise out of probe_all."""

        class ExplodingProber:
            calls = 0

            async def probe(self, base_url: str):
                ExplodingProber.calls += 1
                if ExplodingProber.calls == 1:
                    raise RuntimeError("boom")
                return ("healthy", 50)

        await liveness.probe_all(prober=ExplodingProber())
        assert ExplodingProber.calls == 3
