"""Webhook-level error envelopes.

Webhook handlers receive ONIX-validated traffic in production, but the
endpoint is HTTP-public so any caller can hit it with a body that is not
JSON at all. The default FastAPI ``HTTPException`` for a JSON decode
failure returns 500 — which violates the Beckn contract that callers
always see a NACK envelope on a 4xx response.

We register a single exception handler for ``json.JSONDecodeError`` that
maps it to ``400 NACK``. Other unexpected failures keep their default
behavior (Starlette returns 500) — they are not part of the contract.
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


MALFORMED_JSON_CODE = "MALFORMED_JSON"
MALFORMED_JSON_MESSAGE = "Request body is not valid JSON"


def nack_envelope(*, code: str, message: str) -> dict:
    """Build the Beckn NACK envelope returned on a 4xx error.

    Shape mirrors the synchronous ACK envelope so the BAP/ONIX can parse
    success and failure uniformly: top-level ``message.ack`` carries the
    NACK indicator, and ``error`` carries the machine-readable reason.
    """
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"code": code, "message": message},
    }


async def malformed_json_handler(request: Request, exc: json.JSONDecodeError) -> JSONResponse:
    """Return ``400 NACK`` for any request whose body is not valid JSON."""
    logger.warning(
        "malformed JSON on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=400,
        content=nack_envelope(code=MALFORMED_JSON_CODE, message=MALFORMED_JSON_MESSAGE),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire the error handlers into a FastAPI app.

    Kept as a function (not import-time side effect) so tests can drive
    the same registration on a freshly-constructed app and so both BPPs
    can share the implementation.
    """
    app.add_exception_handler(json.JSONDecodeError, malformed_json_handler)
