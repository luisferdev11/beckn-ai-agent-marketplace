"""CDS stub endpoints — temporary ACK-only behaviour.

Kept here so the routing surface seen by BPPs does not change while
Pieza 3 (Registry) lands. Pieza 1 will fill these in with real publish
+ index logic.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beckn/catalog", tags=["catalog-stub"])


@router.post("")
async def catalog_publish_stub(request: Request):
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    action = body.get("context", {}).get("action", "unknown")
    catalogs = body.get("message", {}).get("catalogs", []) or []
    provider_id = "unknown"
    if catalogs:
        provider_id = catalogs[0].get("provider", {}).get("id", "unknown")
    logger.info("CDS publish (stub) — action=%s provider=%s", action, provider_id)
    return JSONResponse(content={"message": {"ack": {"status": "ACK"}}})


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def catalog_catchall_stub(path: str, request: Request):
    logger.info("CDS catchall (stub) — path=%s", path)
    return JSONResponse(content={"message": {"ack": {"status": "ACK"}}})
