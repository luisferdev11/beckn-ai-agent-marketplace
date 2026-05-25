"""Liveness probe — periodic GET /health against every active subscriber.

Two layers:

  ``HealthProber``        Protocol that maps a URL to a (health, latency)
                          tuple. ``HttpHealthProber`` is the production
                          implementation; tests inject a fake to avoid
                          network I/O.

  ``probe_subscriber``    Translates one probe result into a
                          ``repository.update_health`` call. Holds the
                          consecutive-failure counting policy.

  ``probe_all``           Fans the probe out across all active
                          subscribers. Called by APScheduler.

Probe policy (kept small on purpose so the rules are easy to reason about):

  * Reachable + responsive (< DEGRADED_THRESHOLD_MS)        -> healthy
  * Reachable but slow OR non-2xx response                  -> degraded
  * Connection error / timeout                              -> down
  * On any "down", consecutive_failures += 1 and
    ``last_seen_at`` is NOT touched (we never saw it).
  * On any successful probe, consecutive_failures resets to 0.

The status of a subscriber is intentionally NOT mutated by the probe;
that decision belongs to admins (PATCH /registry/subscribers/{id}). The
probe only updates the health/freshness signals used later by discover
ranking.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.registry import repository

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 5.0
DEGRADED_THRESHOLD_MS = 2000
PROBE_INTERVAL_SECONDS = 60
HEALTH_PATH = "/health"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HealthProber(Protocol):
    """Abstraction over the actual HTTP probe.

    Implementations return ``(health, latency_ms)`` where ``latency_ms``
    is ``-1`` if no connection was established.
    """

    async def probe(self, base_url: str) -> tuple[str, int]: ...


class HttpHealthProber:
    """Production prober — issues a real GET against base_url + /health."""

    def __init__(self, timeout: float = PROBE_TIMEOUT_SECONDS):
        self.timeout = timeout

    async def probe(self, base_url: str) -> tuple[str, int]:
        url = base_url.rstrip("/") + HEALTH_PATH
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            return "down", -1
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("liveness: unexpected probe error for %s: %s", url, exc)
            return "down", -1

        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            return "degraded", latency_ms
        if latency_ms > DEGRADED_THRESHOLD_MS:
            return "degraded", latency_ms
        return "healthy", latency_ms


def _derive_probe_url(subscriber: dict) -> str:
    """Build the base URL we probe for /health.

    Preference order:

      1. ``backend_health_url`` if set — the participant explicitly
         declared which URL to probe. This is the only path that yields
         meaningful liveness signal.
      2. Otherwise strip the Beckn-protocol suffix from ``endpoint_url``
         and probe that (best-effort; ONIX itself does not expose
         /health so this usually marks the subscriber ``down``).
    """
    backend = subscriber.get("backend_health_url")
    if backend:
        return backend.rstrip("/")

    raw = subscriber["endpoint_url"].rstrip("/")
    for suffix in ("/bap/receiver", "/bpp/receiver"):
        if raw.endswith(suffix):
            return raw[: -len(suffix)]
    return raw


async def probe_subscriber(subscriber: dict, prober: HealthProber) -> None:
    """Probe one subscriber and persist the resulting health state.

    No-op for subscribers whose status disqualifies them from probing:
    pending_kyc (not onboarded) and deprecated (retired). Suspended
    subscribers ARE probed so admins can see whether they recovered.
    """
    if subscriber["status"] in ("pending_kyc", "deprecated"):
        return

    base_url = _derive_probe_url(subscriber)
    health, latency_ms = await prober.probe(base_url)

    if health == "down":
        next_failures = subscriber["consecutive_failures"] + 1
        next_last_seen = subscriber["last_seen_at"]
    else:
        next_failures = 0
        next_last_seen = _now_iso()

    await repository.update_health(
        subscriber["subscriber_id"],
        health=health,
        last_seen_at=next_last_seen,
        consecutive_failures=next_failures,
    )

    logger.info(
        "liveness: %s -> %s (latency=%dms, failures=%d)",
        subscriber["subscriber_id"], health, latency_ms, next_failures,
    )


async def probe_all(prober: HealthProber | None = None) -> None:
    """Probe every active or suspended subscriber in parallel.

    Designed to be called by APScheduler. Each individual probe failure
    is contained: one bad subscriber cannot break the others, because
    asyncio.gather is invoked with ``return_exceptions=True``.
    """
    prober = prober or HttpHealthProber()
    subscribers = [
        s for s in await repository.list_subscribers()
        if s["status"] in ("active", "suspended")
    ]
    if not subscribers:
        return
    results = await asyncio.gather(
        *(probe_subscriber(s, prober) for s in subscribers),
        return_exceptions=True,
    )
    for sub, err in zip(subscribers, results):
        if isinstance(err, Exception):
            logger.warning(
                "liveness: probe crashed for %s: %s", sub["subscriber_id"], err
            )
