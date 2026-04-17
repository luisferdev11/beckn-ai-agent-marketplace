"""
BAP-AI — Beckn Application Platform for the AI Agent Marketplace.

This service replaces the sandbox-bap with two capabilities:
1. PASSIVE: receives on_* callbacks from ONIX-BAP (webhook receiver)
2. ACTIVE: exposes API for frontend/scripts to originate Beckn transactions

Iter 0: in-memory storage, hardcoded BPP target, no frontend yet.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import SERVICE_NAME, PORT
from app.routes.webhook import router as webhook_router
from app.routes.api import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(
    title="BAP-AI — Beckn Application Platform",
    version="0.1.0",
    description="AI Agent marketplace buyer backend on Beckn v2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    from app.store import get_callbacks_count
    return {"status": "ok", "service": SERVICE_NAME, "callbacks_recibidos": get_callbacks_count()}


@app.on_event("startup")
async def startup():
    logger.info(f"{SERVICE_NAME} started on port {PORT}")
    logger.info(f"Webhook receiver at /api/bap-webhook/{{action}}")
    logger.info(f"API endpoints at /api/contracts/{{select,init,confirm,status}}")
