"""
BAP webhook receiver — receives on_* callbacks from ONIX-BAP.

This is the passive side of the BAP: ONIX-BAP forwards all on_*
callbacks here after verifying the BPP's signature.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.store import store_callback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bap-webhook", tags=["beckn-webhook"])


@router.post("/{action}")
async def receive_callback(action: str, request: Request):
    """
    Receive any on_* callback from ONIX-BAP.

    ONIX routing sends all on_* actions to /api/bap-webhook/{action}.
    We parse, store, and return ACK.
    """
    body = await request.json()
    context = body.get("context", {})
    message = body.get("message", {})
    txn_id = context.get("transactionId", "unknown")

    logger.info(f"← {action} received [txn={txn_id[:8]}]")

    store_callback(context, message)

    return JSONResponse({"message": {"ack": {"status": "ACK"}}})


@router.post("")
async def receive_callback_root(request: Request):
    """
    Fallback: ONIX may send to /api/bap-webhook without action suffix.
    Extract action from context.
    """
    body = await request.json()
    context = body.get("context", {})
    message = body.get("message", {})
    action = context.get("action", "unknown")
    txn_id = context.get("transactionId", "unknown")

    logger.info(f"← {action} received (root endpoint) [txn={txn_id[:8]}]")

    store_callback(context, message)

    return JSONResponse({"message": {"ack": {"status": "ACK"}}})
