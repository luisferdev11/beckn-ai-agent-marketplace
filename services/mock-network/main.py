"""
Mock Beckn Network Services for local development.

Simulates:
  - DeDi registry (subscriber lookup + public key resolution)
  - CDS (catalog/publish acceptance)

Response format verified against real DeDi API at fabric.nfh.global.
The only difference: `details.url` points to local Docker URIs instead of public URLs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock-network")

app = FastAPI(title="Mock Beckn Network", version="1.0.0")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Exact DeDi response format (verified against fabric.nfh.global/registry/dedi).
# `details.url` overridden to local Docker URIs so ONIX routes within the network.
SUBSCRIBERS: dict[str, dict] = {
    "bap.example.com": {
        "message": "ok",
        "data": {
            "namespace": "beckn-one",
            "namespace_id": "76EU7wu5EJGPXGeM4QxyWf8YEU9N1wYnNmGrEUZMK33PJT3uGRQwK4",
            "registry_id": "76EU8REebknSwWigtj7L6uFrAfpqRMRuXrY3jtpEmv7dpXPB9Zxpwb",
            "registry_name": "example-NPs",
            "record_id": "76EU7LZ7gfqj13dWDKR1Uitnim11mCoxWBPdzLxUpAMBPVdANKgyFM",
            "record_name": "example-bap",
            "description": "Subscription details",
            "details": {
                "subscriber_id": "bap.example.com",
                "url": "http://onix-bap:8081/bap/receiver",
                "type": "BAP",
                "domain": "*",
                "countries": ["IND"],
                "signing_public_key": "g/3swjI93IhZ0SScrVZapeLjU+W0AeiSid3LViYZJFo=",
            },
            "meta": {},
            "parent_namespaces": ["beckn.one", "nfh.global"],
            "network_memberships": ["beckn.one/testnet"],
            "state": "live",
            "ttl": 600,
        },
    },
    "bpp.example.com": {
        "message": "ok",
        "data": {
            "namespace": "beckn-one",
            "namespace_id": "76EU7wu5EJGPXGeM4QxyWf8YEU9N1wYnNmGrEUZMK33PJT3uGRQwK4",
            "registry_id": "76EU8REebknSwWigtj7L6uFrAfpqRMRuXrY3jtpEmv7dpXPB9Zxpwb",
            "registry_name": "example-NPs",
            "record_id": "76EU7ofwRCF1aobQkShARrf1PAUsNpHqWUJoynPu9w45YFKmzqaPmy",
            "record_name": "example-bpp",
            "description": "Subscription details",
            "details": {
                "subscriber_id": "bpp.example.com",
                "url": "http://onix-bpp:8082/bpp/receiver",
                "type": "BPP",
                "domain": "*",
                "countries": ["IND"],
                "signing_public_key": "CqVy97DW45bcZPPrWIYGe2ldl9C93NFeVciiAEYsvR0=",
            },
            "meta": {},
            "parent_namespaces": ["beckn.one", "nfh.global"],
            "network_memberships": ["beckn.one/testnet"],
            "state": "live",
            "ttl": 600,
        },
    },
}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-beckn-network", "time": _now_iso()}


# ─── DeDi Registry ────────────────────────────────────────────────────────────
# ONIX calls: GET /registry/dedi/lookup/{subscriber_id}/{registry_name}/{key_id}

@app.get("/registry/dedi/lookup/{subscriber_id}/{registry_name}/{key_id}")
async def dedi_lookup_by_path(subscriber_id: str, registry_name: str, key_id: str):
    logger.info("DeDi lookup — subscriber_id=%s key_id=%s", subscriber_id, key_id)
    response = SUBSCRIBERS.get(subscriber_id)
    if not response:
        logger.warning("DeDi lookup: unknown subscriber %s", subscriber_id)
        return JSONResponse(status_code=404, content={"message": "not found"})
    return JSONResponse(content=response)


@app.get("/registry/dedi/lookup/{subscriber_id}/{registry_name}")
async def dedi_lookup_by_path_no_key(subscriber_id: str, registry_name: str):
    logger.info("DeDi lookup — subscriber_id=%s", subscriber_id)
    response = SUBSCRIBERS.get(subscriber_id)
    if not response:
        return JSONResponse(status_code=404, content={"message": "not found"})
    return JSONResponse(content=response)


@app.post("/registry/dedi/lookup")
@app.post("/registry/dedi")
@app.post("/lookup")
async def dedi_lookup_post(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    subscriber_id = body.get("subscriber_id") or body.get("subscriberId") or body.get("id")
    logger.info("DeDi lookup POST — subscriber_id=%s", subscriber_id)
    response = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not response:
        response = list(SUBSCRIBERS.values())[0]
    return JSONResponse(content=response)


@app.get("/registry/dedi")
async def dedi_lookup_get(request: Request):
    params = dict(request.query_params)
    subscriber_id = params.get("subscriber_id") or params.get("id")
    logger.info("DeDi lookup GET — subscriber_id=%s", subscriber_id)
    response = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not response:
        response = list(SUBSCRIBERS.values())[0]
    return JSONResponse(content=response)


@app.api_route("/registry/dedi/{path:path}", methods=["GET", "POST"])
async def dedi_catchall(path: str, request: Request):
    parts = path.strip("/").split("/")
    # Path: lookup/{subscriber_id}/{registry_name}/{key_id}
    subscriber_id = parts[1] if len(parts) > 1 else parts[0] if parts else None
    logger.info("DeDi catchall — path=%s subscriber_id=%s", path, subscriber_id)
    response = SUBSCRIBERS.get(subscriber_id) if subscriber_id else None
    if not response:
        response = list(SUBSCRIBERS.values())[0]
    return JSONResponse(content=response)


# ─── CDS (Catalog Discovery Service) ─────────────────────────────────────────

@app.post("/beckn/catalog")
async def catalog_publish(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    action = body.get("context", {}).get("action", "unknown")
    provider_id = body.get("message", {}).get("catalog", {}).get("provider", {}).get("id", "unknown")
    logger.info("CDS publish — action=%s provider=%s", action, provider_id)
    return JSONResponse(content={"message": {"ack": {"status": "ACK"}}})


@app.api_route("/beckn/catalog/{path:path}", methods=["GET", "POST"])
async def catalog_catchall(path: str, request: Request):
    logger.info("CDS catchall — path=%s", path)
    return JSONResponse(content={"message": {"ack": {"status": "ACK"}}})
