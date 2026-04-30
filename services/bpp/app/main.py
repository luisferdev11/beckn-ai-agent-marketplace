"""
BPP-AI — Beckn Provider Platform for the AI Agent Marketplace.

This service:
- Receives Beckn actions (select, init, confirm, etc.) from ONIX-BPP
- Manages a catalog of AI agents in PostgreSQL
- Processes contracts with real pricing logic
- Sends on_* callbacks back through ONIX-BPP
- Exposes CRUD API for provider portal (categories, providers, agents)
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import SERVICE_NAME, PORT
from app.routes.webhook import router as webhook_router
from app.routes.provider_api import router as provider_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(
    title="BPP-AI — Beckn Provider Platform",
    version="0.2.0",
    description="AI Agent marketplace provider backend on Beckn v2.0.0 with PostgreSQL",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(provider_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.on_event("startup")
async def startup():
    from beckn_models.db import get_pool
    await get_pool()
    logger.info(f"{SERVICE_NAME} started on port {PORT} — PostgreSQL connected")
    logger.info(f"Webhook: /api/webhook/{{action}}")
    logger.info(f"Provider API: /api/{{categories,providers,agents,publish}}")


@app.on_event("shutdown")
async def shutdown():
    from beckn_models.db import close_pool
    await close_pool()
    logger.info("PostgreSQL pool closed")
