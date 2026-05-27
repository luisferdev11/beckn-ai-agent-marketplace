"""Composite scoring used by discover to rank candidate agents.

Formula (briefing §3.2 / ROADMAP "Bloqueante for production-minimal"):

    score = SEMANTIC_WEIGHT  * semantic_similarity
          + FRESHNESS_WEIGHT * freshness_score(published_at)
          + HEALTH_WEIGHT    * health_score(subscriber.health)

The functions take primitive inputs (similarity floats, datetimes, raw
``health`` strings) so they unit-test cleanly without a DB or embedder.
The caller (``app.discover.query``) is responsible for collecting these
inputs via SQL and assembling the score per row.

Why split into three pure functions rather than collapse into one SQL
expression: keeping the math in Python gives us readable scoring rules,
exact unit tests, and the freedom to change the freshness curve without
a migration. The candidate set returned by SQL is already small (filters
shrink it before scoring), so the extra Python work is negligible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# Weights. Changing these is a deliberate, observable change — tests pin
# the ratios (semantic dominant, freshness == health).
SEMANTIC_WEIGHT: float = 0.6
FRESHNESS_WEIGHT: float = 0.2
HEALTH_WEIGHT: float = 0.2

FRESHNESS_WINDOW_DAYS: int = 90

# Registry ``subscribers.health`` → numeric contribution.
# ``unknown`` and missing values default to neutral (0.5) so a brand-new
# BPP that hasn't been probed yet is not punished.
_HEALTH_MAP: dict[str, float] = {
    "healthy": 1.0,
    "degraded": 0.5,
    "unhealthy": 0.0,
    "unknown": 0.5,
}
_HEALTH_DEFAULT: float = 0.5


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def freshness_score(*, published_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    """Linear decay over ``FRESHNESS_WINDOW_DAYS`` from ``published_at``.

    Returns 1.0 when ``published_at`` is now or in the future (clock skew
    tolerance), 0.0 once the agent is older than the window, and a
    linear interpolation in between. ``None`` is treated as maximally
    stale — we'd rather demote an unstamped agent than over-rank it.
    """
    if published_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    # Make both sides comparable: if either is naive, treat as UTC.
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = (now - published_at).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    score = 1.0 - (age_days / FRESHNESS_WINDOW_DAYS)
    return _clamp(score)


def health_score(health: Optional[str]) -> float:
    """Map Registry ``subscribers.health`` to a numeric contribution.

    Unknown / missing → 0.5 (neutral). Any string the Registry might
    grow in the future falls into the same default rather than crashing
    the scorer.
    """
    if health is None:
        return _HEALTH_DEFAULT
    return _HEALTH_MAP.get(health, _HEALTH_DEFAULT)


def composite_score(*, semantic: float, freshness: float, health: float) -> float:
    """Combine the three component scores with the static weights.

    Inputs are clamped to ``[0.0, 1.0]`` so pgvector's occasionally-noisy
    cosine output (mildly negative or slightly above 1.0) cannot produce
    a composite outside the documented range.
    """
    s = _clamp(semantic)
    f = _clamp(freshness)
    h = _clamp(health)
    return SEMANTIC_WEIGHT * s + FRESHNESS_WEIGHT * f + HEALTH_WEIGHT * h
