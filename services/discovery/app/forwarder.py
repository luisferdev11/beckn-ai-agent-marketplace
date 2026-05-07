"""
Fan-out forwarder — POSTs the discover payload to every registered BPP receiver.

Each BPP runs independently. One failing must not block the others, so we
gather with return_exceptions and just log per-BPP outcomes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import BppEntry

logger = logging.getLogger(__name__)


async def _post_one(
    client: httpx.AsyncClient,
    bpp: BppEntry,
    body: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    target = f"{bpp.receiver_url}/discover"
    try:
        resp = await client.post(target, json=body, headers=headers)
        return {
            "subscriber_id": bpp.subscriber_id,
            "url": target,
            "status_code": resp.status_code,
            "ok": 200 <= resp.status_code < 300,
        }
    except httpx.HTTPError as exc:
        logger.warning("forward to %s failed: %s", target, exc)
        return {
            "subscriber_id": bpp.subscriber_id,
            "url": target,
            "status_code": None,
            "ok": False,
            "error": str(exc),
        }


async def fan_out(
    bpps: list[BppEntry],
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """POST body to every BPP receiver in parallel. Never raises."""
    if not bpps:
        return []

    headers = {k: v for k, v in (headers or {}).items() if k.lower() != "host"}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        tasks = [_post_one(client, bpp, body, headers) for bpp in bpps]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    for r in results:
        marker = "✓" if r.get("ok") else "✗"
        logger.info("fan-out %s %s [%s]", marker, r["subscriber_id"], r.get("status_code"))

    return results
