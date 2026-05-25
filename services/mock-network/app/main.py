"""Mock-network FastAPI entry point.

Wires the logically independent surfaces (DeDi, Registry, Catalog stub)
into a single ASGI app. Owns the Postgres pool lifecycle so each
submodule can simply pull the pool when it needs it.

This is Pieza 3 of the discover v2 redesign: the Registry plus the
foundation for the next pieces (Catalog publish in Pieza 1, Discover
in Pieza 2). The Catalog routes are currently stubs — Pieza 1 replaces
them with real publish+index logic.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.catalog.routes import router as catalog_router
from app.config import SERVICE_NAME
from app.db.pool import close_pool, get_pool
from app.dedi.routes import router as dedi_router
from app.registry import liveness
from app.registry.routes import router as registry_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Establish the pool on startup so the first request does not pay the
    # connection cost; close it on shutdown so the container can exit
    # cleanly without leaving idle backends on postgres-mocknet.
    await get_pool()

    # Start the liveness probe scheduler. It hits GET /health on every
    # active/suspended subscriber every PROBE_INTERVAL_SECONDS so the
    # discover-time freshness score reflects reality.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        liveness.probe_all,
        trigger=IntervalTrigger(seconds=liveness.PROBE_INTERVAL_SECONDS),
        id="registry.liveness.probe_all",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "%s started — DeDi mock + Registry + Catalog stub; liveness probe every %ss",
        SERVICE_NAME, liveness.PROBE_INTERVAL_SECONDS,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await close_pool()


app = FastAPI(
    title="Mock Beckn Network",
    version="2.0.0",
    description=(
        "Local stand-in for the Beckn network services we cannot run with "
        "our own identities: DeDi (signature lookups), Registry (BPP/BAP "
        "onboarding state, Pieza 3), and a CDS stub (Pieza 1 placeholder)."
    ),
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


app.include_router(dedi_router)
app.include_router(registry_router)
app.include_router(catalog_router)
