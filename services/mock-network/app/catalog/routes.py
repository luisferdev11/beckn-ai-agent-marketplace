"""CDS HTTP surface — catalog/publish.

This is now a real handler (replaces the Pieza 3 stub). The endpoint
returns ACK synchronously per Beckn v2 and runs the actual indexing in
a BackgroundTasks task; on_publish is delivered to the BPP backend
once indexing finishes.

A note on routing layout: the BPP posts to ``/beckn/catalog`` (the path
ONIX-BPP forwards to per ``infra/onix/generic-routing-BPPCaller.yaml``).
The shape of the payload distinguishes publish vs other catalog ops
(only publish exists for now).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.catalog import service as catalog_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beckn/catalog", tags=["catalog"])


def _ack() -> dict:
    return {"message": {"ack": {"status": "ACK"}}}


def _nack(error_code: str, message: str) -> dict:
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"code": error_code, "message": message},
    }


async def _process_and_callback(envelope: dict) -> None:
    """Background task: run the publish pipeline then deliver on_publish.

    Wrapping in try/except so the BPP always sees a callback, even if a
    bug in the pipeline raises late — the alternative (silent failure)
    is the worst possible UX for a publish flow.
    """
    try:
        results = await catalog_service.process_publish(envelope)
    except Exception as exc:  # noqa: BLE001
        logger.exception("catalog/publish: pipeline crashed: %s", exc)
        results = [{
            "catalogId": None,
            "status": "REJECTED",
            "stats": {"itemCount": 0, "itemCountAccepted": 0, "itemCountRejected": 0},
            "errors": [{"resourceId": "", "code": "PIPELINE_ERROR", "message": str(exc), "path": "$"}],
        }]
    await catalog_service.dispatch_on_publish(envelope, results)


@router.post("")
@router.post("/publish")
async def catalog_publish(request: Request, background: BackgroundTasks):
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content=_nack("INVALID_JSON", "request body is not valid JSON"))

    context = body.get("context") or {}
    txn = context.get("transactionId") or "unknown"
    bpp = context.get("bppId") or "unknown"

    if not body.get("message") or not (body["message"].get("catalogs") or []):
        return JSONResponse(
            status_code=400,
            content=_nack("EMPTY_CATALOG", "message.catalogs is empty or missing"),
        )

    logger.info(
        "catalog/publish: accepted [txn=%s bpp=%s catalogs=%d]",
        txn[:8] if isinstance(txn, str) else txn,
        bpp,
        len(body["message"]["catalogs"]),
    )

    background.add_task(_process_and_callback, body)
    return JSONResponse(content=_ack())


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def catalog_catchall_stub(path: str, request: Request):
    """Tolerant fallback for any non-publish catalog path we have not
    implemented yet (subscription, pull, etc.). Returns ACK so BPPs/BAPs
    that try newer ops do not hard-fail; we'll fill these in as the
    spec surface gets implemented."""
    logger.info("catalog catchall (stub) — path=%s", path)
    return JSONResponse(content=_ack())


# ─── Operator introspection ───────────────────────────────────────


operator_router = APIRouter(prefix="/cds", tags=["cds-operator"])


@operator_router.get("/stats")
async def cds_stats():
    """Quick visibility for the operator and smoke tests."""
    from app.catalog import repository
    current_total = await repository.count_current_agents()
    return {
        "index": {
            "current_agents_total": current_total,
        },
    }
