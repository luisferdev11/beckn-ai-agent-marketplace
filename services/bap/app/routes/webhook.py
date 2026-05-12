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


def _merge_error(message: dict, body: dict) -> dict:
    """Preserve Beckn top-level `error` inside the stored message JSONB.

    Beckn v2 returns business errors (e.g. 30002 transaction-not-found, see
    issue #14) at the envelope root next to context/message. We embed it in
    `message._error` so the existing audit log surfaces it without a schema
    migration.
    """
    error = body.get("error")
    if error:
        return {**message, "_error": error}
    return message


@router.post("/{action}")
async def receive_callback(action: str, request: Request):
    """
    Receive any on_* callback from ONIX-BAP.

    ONIX routing sends all on_* actions to /api/bap-webhook/{action}.
    We parse, store, and return ACK.
    """
    body = await request.json()
    context = body.get("context", {})
    message = _merge_error(body.get("message", {}), body)
    txn_id = context.get("transactionId", "unknown")

    if "_error" in message:
        logger.warning(
            f"← {action} received [txn={txn_id[:8]}] with error "
            f"{message['_error'].get('code')}: {message['_error'].get('message')}"
        )
    else:
        logger.info(f"← {action} received [txn={txn_id[:8]}]")

    await store_callback(context, message)

    return JSONResponse({"message": {"ack": {"status": "ACK"}}})


@router.post("")
async def receive_callback_root(request: Request):
    """
    Fallback: ONIX may send to /api/bap-webhook without action suffix.
    Extract action from context.
    """
    body = await request.json()
    context = body.get("context", {})
    message = _merge_error(body.get("message", {}), body)
    action = context.get("action", "unknown")
    txn_id = context.get("transactionId", "unknown")

    logger.info(f"← {action} received (root endpoint) [txn={txn_id[:8]}]")

    await store_callback(context, message)

    return JSONResponse({"message": {"ack": {"status": "ACK"}}})
