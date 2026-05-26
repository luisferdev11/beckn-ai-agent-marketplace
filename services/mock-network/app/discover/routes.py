"""CDS HTTP surface — beckn discover.

POST /beckn/discover

  Sync:  returns Beckn ACK envelope.
  Async: builds on_discover and POSTs it to the BAP backend.

The current routing scheme expects the BAP to call ``/beckn/discover``
via ONIX-BAP (see infra/onix/generic-routing-BAPCaller.yaml). The
inbound payload is a standard Beckn v2 discover envelope; see
``app.discover.models.from_envelope`` for how we parse it.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.discover import service as discover_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beckn", tags=["discover"])


def _ack() -> dict:
    return {"message": {"ack": {"status": "ACK"}}}


def _nack(code: str, message: str) -> dict:
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"code": code, "message": message},
    }


async def _process_and_callback(envelope: dict) -> None:
    """Background task: build on_discover, dispatch to BAP.

    Wrapped in try/except: a buggy retrieval (e.g. DB hiccup) must not
    leave the BAP hanging on a callback that never arrives. We log and
    drop; the BAP can issue a fresh discover whenever it likes.
    """
    try:
        on_discover_envelope = await discover_service.process_discover(envelope)
    except Exception as exc:  # noqa: BLE001
        logger.exception("discover: pipeline crashed: %s", exc)
        return
    await discover_service.dispatch_on_discover(on_discover_envelope)


@router.post("/discover")
async def discover_endpoint(request: Request, background: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=_nack("INVALID_JSON", "request body is not valid JSON"),
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content=_nack("INVALID_BODY", "request body must be an object"),
        )

    context = body.get("context") or {}
    txn = context.get("transactionId") or "unknown"
    bap = context.get("bapId") or "unknown"

    logger.info(
        "discover: accepted [txn=%s bap=%s]",
        txn[:8] if isinstance(txn, str) else txn, bap,
    )

    background.add_task(_process_and_callback, body)
    return JSONResponse(content=_ack())
