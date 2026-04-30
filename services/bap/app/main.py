"""
BAP-AI — Beckn Application Platform for the AI Agent Marketplace.

This service:
1. PASSIVE: receives on_* callbacks from ONIX-BAP (webhook receiver)
2. ACTIVE: exposes API for frontend/scripts to originate Beckn transactions

PostgreSQL backed — callbacks and transactions persisted.
"""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    version="0.2.0",
    description="AI Agent marketplace buyer backend on Beckn v2.0.0 with PostgreSQL",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(api_router)


@app.exception_handler(httpx.ConnectError)
async def onix_connect_error_handler(request: Request, exc: httpx.ConnectError):
    return JSONResponse(status_code=503, content={"error": "ONIX unavailable", "detail": str(exc)})


@app.exception_handler(httpx.TimeoutException)
async def onix_timeout_handler(request: Request, exc: httpx.TimeoutException):
    return JSONResponse(status_code=504, content={"error": "ONIX timeout", "detail": str(exc)})


@app.get("/health")
async def health():
    from app.store import get_callbacks_count
    count = await get_callbacks_count()
    return {"status": "ok", "service": SERVICE_NAME, "callbacks_recibidos": count}


@app.on_event("startup")
async def startup():
    from beckn_models.db import get_pool
    await get_pool()
    logger.info(f"{SERVICE_NAME} started on port {PORT} — PostgreSQL connected")


@app.on_event("shutdown")
async def shutdown():
    from beckn_models.db import close_pool
    await close_pool()
    logger.info("PostgreSQL pool closed")
