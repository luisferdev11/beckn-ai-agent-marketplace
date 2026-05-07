"""
BPP webhook routes — receives Beckn actions from ONIX-BPP.

ONIX-BPP forwards validated requests here. We:
1. Return ACK synchronously (fast, <100ms)
2. Process the action and build the on_* response
3. POST the on_* callback to ONIX-BPP at /bpp/caller/on_{action}
   (ONIX then signs it and sends it to the BAP)
"""

import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.config import BPP_CALLBACK_URL
from app.handlers.beckn_actions import ACTION_HANDLERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["beckn-webhook"])


async def _send_callback(callback_url: str, payload: dict, action: str, txn_id: str):
    """Send the on_* callback to ONIX-BPP asynchronously."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(callback_url, json=payload)
            logger.info(
                f"callback on_{action} sent to {callback_url} "
                f"[txn={txn_id[:8]}] → HTTP {response.status_code}"
            )
    except Exception as e:
        logger.error(f"callback on_{action} failed [txn={txn_id[:8]}]: {e}")


@router.post("/{action}")
async def handle_beckn_action(action: str, request: Request, background: BackgroundTasks):
    """
    Generic handler for all Beckn actions.

    ONIX-BPP routes all actions here: select, init, confirm, status,
    cancel, rating, support, track, update, on_publish.
    """
    body = await request.json()
    context = body.get("context", {})
    message = body.get("message", {})
    txn_id = context.get("transactionId", "unknown")

    logger.info(f"← {action} received [txn={txn_id[:8]}]")

    # Special case: on_publish is a confirmation from CDS, just log it
    if action == "on_publish":
        logger.info(f"on_publish received — catalog published successfully [txn={txn_id[:8]}]")
        return JSONResponse({"message": {"ack": {"status": "ACK"}}})

    # Find the handler for this action
    handler = ACTION_HANDLERS.get(action)
    if not handler:
        logger.warning(f"no handler for action '{action}', echoing back as sandbox would")
        # Fallback: echo like the sandbox does (just change action to on_*)
        callback_payload = {
            "context": {**context, "action": f"on_{action}"},
            "message": message,
        }
        callback_url = f"{BPP_CALLBACK_URL}/on_{action}"
        background.add_task(_send_callback, callback_url, callback_payload, action, txn_id)
        return JSONResponse({"message": {"ack": {"status": "ACK"}}})

    # Build the on_* response
    callback_payload = await handler(context, message)

    # Send callback async (don't block the ACK response)
    callback_url = f"{BPP_CALLBACK_URL}/on_{action}"
    background.add_task(_send_callback, callback_url, callback_payload, action, txn_id)

    # Return ACK immediately
    return JSONResponse({"message": {"ack": {"status": "ACK"}}})
