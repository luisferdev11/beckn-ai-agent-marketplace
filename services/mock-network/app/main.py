"""Mock-network FastAPI entry point.

Wires the logically independent surfaces (DeDi, Registry, Catalog,
CDS operator) into a single ASGI app. Owns the Postgres pool lifecycle
so each submodule can simply pull the pool when it needs it.

After Pieza 1 the Catalog routes are real (publish + index). Discover
arrives in Pieza 2 as a separate submodule.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.catalog.routes import operator_router as cds_operator_router
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
    await get_pool()

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
        "%s started — DeDi + Registry + Catalog publish; liveness probe every %ss",
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
        "onboarding state), CDS catalog publish + index."
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
app.include_router(cds_operator_router)
