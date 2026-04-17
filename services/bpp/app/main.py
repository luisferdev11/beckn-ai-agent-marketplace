"""
BPP-AI — Beckn Provider Platform for the AI Agent Marketplace.

This service replaces the sandbox-bpp with real business logic:
- Receives Beckn actions (select, init, confirm, etc.) from ONIX-BPP
- Manages a catalog of AI agents
- Processes contracts with real pricing logic
- Sends on_* callbacks back through ONIX-BPP

Iter 0: mock agent execution, in-memory contract storage, hardcoded catalog.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import SERVICE_NAME, PORT
from app.routes.webhook import router as webhook_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(
    title="BPP-AI — Beckn Provider Platform",
    version="0.1.0",
    description="AI Agent marketplace provider backend on Beckn v2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api/catalog")
async def get_catalog():
    """Return the full catalog of AI agents (utility endpoint for debugging)."""
    from app.catalog_data import get_catalog_for_publish
    return get_catalog_for_publish()


@app.post("/api/catalog/publish")
async def publish_catalog():
    """
    Publish our AI agent catalog to the Beckn CDS (Catalog Discovery Service).

    Sends catalog/publish to ONIX-BPP, which signs it and forwards to
    fabric.nfh.global/beckn/catalog. The CDS responds async with on_publish.
    """
    import uuid
    from datetime import datetime, timezone
    import httpx
    from app.catalog_data import get_catalog_for_publish
    from app.config import BPP_CALLBACK_URL, BPP_ID, BPP_URI, NETWORK_ID

    dt = datetime.now(timezone.utc)
    timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    payload = {
        "context": {
            "networkId": NETWORK_ID,
            "action": "catalog/publish",
            "version": "2.0.0",
            "bapId": "bap.example.com",
            "bapUri": "http://onix-bap:8081/bap/receiver",
            "bppId": BPP_ID,
            "bppUri": BPP_URI,
            "transactionId": str(uuid.uuid4()),
            "messageId": str(uuid.uuid4()),
            "timestamp": timestamp,
            "ttl": "PT30S",
        },
        "message": {
            "catalogs": [get_catalog_for_publish()],
        },
    }

    publish_url = f"{BPP_CALLBACK_URL.replace('/bpp/caller', '/bpp/caller')}/publish"
    # The publish endpoint in ONIX is at /bpp/caller/publish (same base as callbacks)
    # but the routing config sends it to fabric.nfh.global/beckn/catalog

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(publish_url, json=payload)
            result = response.json()
            logger.info(f"publish sent to CDS — HTTP {response.status_code}")
            return {
                "status": "sent",
                "http_code": response.status_code,
                "onix_response": result,
                "transactionId": payload["context"]["transactionId"],
            }
    except Exception as e:
        logger.error(f"publish failed: {e}")
        return {"status": "error", "detail": str(e)}


@app.get("/api/contracts")
async def list_contracts():
    """List all contracts in memory (utility endpoint for debugging)."""
    from app.handlers.beckn_actions import _contracts
    return {"contracts": list(_contracts.values()), "total": len(_contracts)}


@app.on_event("startup")
async def startup():
    logger.info(f"{SERVICE_NAME} started on port {PORT}")
    logger.info(f"Webhook endpoints at /api/webhook/{{action}}")
    logger.info(f"Catalog: 3 AI agents (summarizer, code-reviewer, data-extractor)")
    logger.info(f"Publish catalog: POST /api/catalog/publish")
