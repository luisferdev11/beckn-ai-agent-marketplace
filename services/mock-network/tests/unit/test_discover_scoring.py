"""Pure-function tests for the composite discover score.

Composite score (briefing §3.2 / ROADMAP "Bloqueante for production-minimal"):

    score = 0.6 * semantic + 0.2 * freshness + 0.2 * health

Each component lives in 0.0..1.0 so the composite is also bounded in
0.0..1.0. The weights are static module-level constants; behavioural
tests pin the weight choices so a future change is a deliberate change.

Component definitions:

  semantic   — cosine similarity returned by pgvector (already normalised
               into 0..1 by the existing query). 0.0 when there is no
               text_search.
  freshness  — linear decay over a 90-day window from ``published_at``:
                  age <=  0 d   -> 1.0
                  age >= 90 d   -> 0.0
                  otherwise     -> 1 - age_days / 90
  health     — Registry ``subscribers.health`` mapped onto a float:
                  "healthy"   -> 1.0
                  "degraded"  -> 0.5
                  "unhealthy" -> 0.0
                  "unknown"   -> 0.5
                  anything else / missing -> 0.5

These functions take primitive inputs so we can test them in isolation
without touching Postgres, the embedder, or the route layer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.discover.scoring import (
    SEMANTIC_WEIGHT,
    FRESHNESS_WEIGHT,
    HEALTH_WEIGHT,
    composite_score,
    freshness_score,
    health_score,
)


# ── Weights pinned ─────────────────────────────────────────────────


class TestWeightsAreThePublishedContract:
    def test_weights_sum_to_one(self):
        assert SEMANTIC_WEIGHT + FRESHNESS_WEIGHT + HEALTH_WEIGHT == pytest.approx(1.0)

    def test_semantic_is_dominant_weight(self):
        assert SEMANTIC_WEIGHT > FRESHNESS_WEIGHT
        assert SEMANTIC_WEIGHT > HEALTH_WEIGHT

    def test_freshness_and_health_have_equal_weight(self):
        assert FRESHNESS_WEIGHT == HEALTH_WEIGHT


# ── Freshness ──────────────────────────────────────────────────────


class TestFreshnessScore:
    def test_just_published_is_one(self):
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        assert freshness_score(published_at=now, now=now) == pytest.approx(1.0)

    def test_published_45_days_ago_is_half(self):
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        published = now - timedelta(days=45)
        assert freshness_score(published_at=published, now=now) == pytest.approx(0.5)

    def test_published_90_days_ago_is_zero(self):
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        published = now - timedelta(days=90)
        assert freshness_score(published_at=published, now=now) == pytest.approx(0.0)

    def test_published_beyond_window_clamps_to_zero(self):
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        published = now - timedelta(days=400)
        assert freshness_score(published_at=published, now=now) == 0.0

    def test_missing_published_at_returns_zero(self):
        # An indexed agent with no published_at is treated as maximally stale.
        # This is conservative — we'd rather demote it than over-rank it.
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        assert freshness_score(published_at=None, now=now) == 0.0

    def test_future_published_at_clamps_to_one(self):
        # Clock skew in upstream BPPs can produce future timestamps; clamp
        # rather than producing >1.0 which would break the composite range.
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)
        future = now + timedelta(days=5)
        assert freshness_score(published_at=future, now=now) == pytest.approx(1.0)


# ── Health ─────────────────────────────────────────────────────────


class TestHealthScore:
    def test_healthy_is_one(self):
        assert health_score("healthy") == 1.0

    def test_degraded_is_half(self):
        assert health_score("degraded") == 0.5

    def test_unhealthy_is_zero(self):
        assert health_score("unhealthy") == 0.0

    def test_unknown_is_half(self):
        # "unknown" is the seed default for subscribers that have not yet
        # been probed. Defaulting to 0.5 keeps brand-new BPPs visible
        # without privileging them over confirmed-healthy peers.
        assert health_score("unknown") == 0.5

    def test_none_defaults_to_half(self):
        assert health_score(None) == 0.5

    def test_garbage_value_defaults_to_half(self):
        # Forward-compatibility: a new Registry health value should not
        # crash the scorer; demote to neutral.
        assert health_score("flaky-but-recovering") == 0.5


# ── Composite ──────────────────────────────────────────────────────


class TestCompositeScore:
    def test_zero_inputs_give_zero(self):
        assert composite_score(semantic=0.0, freshness=0.0, health=0.0) == 0.0

    def test_perfect_inputs_give_one(self):
        score = composite_score(semantic=1.0, freshness=1.0, health=1.0)
        assert score == pytest.approx(1.0)

    def test_semantic_only_at_max_yields_semantic_weight(self):
        # With freshness=health=0, the composite equals SEMANTIC_WEIGHT.
        assert composite_score(semantic=1.0, freshness=0.0, health=0.0) == pytest.approx(
            SEMANTIC_WEIGHT
        )

    def test_health_only_at_max_yields_health_weight(self):
        assert composite_score(semantic=0.0, freshness=0.0, health=1.0) == pytest.approx(
            HEALTH_WEIGHT
        )

    def test_clamps_negative_semantic(self):
        # pgvector can return a small negative when vectors point opposite.
        # The composite should treat negative similarity as 0.0.
        assert composite_score(semantic=-0.1, freshness=1.0, health=1.0) == pytest.approx(
            FRESHNESS_WEIGHT + HEALTH_WEIGHT
        )

    def test_clamps_semantic_above_one(self):
        # Defensive: floating-point can drift slightly above 1.0; cap it.
        assert composite_score(semantic=1.01, freshness=0.0, health=0.0) <= 1.0


class TestCompositeRanksAsExpected:
    """End-to-end behavioural pins. The exact numbers fall out of the
    weights, but the *ordering* is what the BAP relies on."""

    def test_fresh_healthy_beats_stale_healthy_at_same_similarity(self):
        fresh = composite_score(semantic=0.5, freshness=1.0, health=1.0)
        stale = composite_score(semantic=0.5, freshness=0.0, health=1.0)
        assert fresh > stale

    def test_healthy_beats_unhealthy_at_same_similarity(self):
        healthy = composite_score(semantic=0.5, freshness=0.5, health=1.0)
        unhealthy = composite_score(semantic=0.5, freshness=0.5, health=0.0)
        assert healthy > unhealthy

    def test_high_semantic_dominates_freshness_and_health(self):
        # A perfectly-relevant brand-new healthy agent should outrank a
        # weakly-relevant pristine agent (semantic weight is dominant).
        relevant = composite_score(semantic=0.9, freshness=0.0, health=0.0)
        irrelevant = composite_score(semantic=0.1, freshness=1.0, health=1.0)
        assert relevant > irrelevant
