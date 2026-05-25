"""DeDi lookup endpoints — preserves the routing surface ONIX expects.

The four shapes below all return the same SubscriberRecord payload
because ONIX implementations call DeDi through slightly different paths
(historical drift). All shapes resolve against the hardcoded
``SUBSCRIBERS`` dict in ``app.dedi.data``.

If a subscriber id is unknown we return either 404 (path-style lookups
where the id is part of the URL) or the first known record (POST/GET
discovery-style lookups where ONIX expects a non-empty payload). The
inconsistency is intentional and matches what ONIX gracefully tolerates.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.dedi.data import SUBSCRIBERS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dedi"])


@router.get("/registry/dedi/lookup/{subscriber_id}/{registry_name}/{key_id}")
async def dedi_lookup_by_path(subscriber_id: str, registry_name: str, key_id: str):
    logger.info("DeDi lookup — subscriber_id=%s key_id=%s", subscriber_id, key_id)
    record = SUBSCRIBERS.get(subscriber_id)
    if not record:
        logger.warning("DeDi lookup: unknown subscriber %s", subscriber_id)
        return JSONResponse(status_code=404, content={"message": "not found"})
    return JSONResponse(content=record)


@router.get("/registry/dedi/lookup/{subscriber_id}/{registry_name}")
async def dedi_lookup_by_path_no_key(subscriber_id: str, registry_name: str):
    logger.info("DeDi lookup — subscriber_id=%s", subscriber_id)
    record = SUBSCRIBERS.get(subscriber_id)
    if not record:
        return JSONResponse(status_code=404, content={"message": "not found"})
    return JSONResponse(content=record)


@router.post("/registry/dedi/lookup")
@router.post("/registry/dedi")
@router.post("/lookup")
async def dedi_lookup_post(request: Request):
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    subscriber_id = body.get("subscriber_id") or body.get("subscriberId") or body.get("id")
    logger.info("DeDi lookup POST — subscriber_id=%s", subscriber_id)
    record = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not record:
        record = next(iter(SUBSCRIBERS.values()))
    return JSONResponse(content=record)


@router.get("/registry/dedi")
async def dedi_lookup_get(request: Request):
    params = dict(request.query_params)
    subscriber_id = params.get("subscriber_id") or params.get("id")
    logger.info("DeDi lookup GET — subscriber_id=%s", subscriber_id)
    record = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not record:
        record = next(iter(SUBSCRIBERS.values()))
    return JSONResponse(content=record)


@router.api_route("/registry/dedi/{path:path}", methods=["GET", "POST"])
async def dedi_catchall(path: str, request: Request):
    parts = path.strip("/").split("/")
    # Path layout used by some ONIX versions: lookup/{subscriber_id}/{registry_name}/{key_id}
    subscriber_id = parts[1] if len(parts) > 1 else (parts[0] if parts else None)
    logger.info("DeDi catchall — path=%s subscriber_id=%s", path, subscriber_id)
    record = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not record:
        record = next(iter(SUBSCRIBERS.values()))
    return JSONResponse(content=record)
