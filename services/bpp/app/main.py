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
