"""Webhook-level error envelopes.

Mirrors ``services/bpp/app/errors.py``. Kept as a per-service module
(instead of shared lib) because the two BPPs run as independent
deployables and can drift on their error-mapping policy if needed.
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
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"code": code, "message": message},
    }


async def malformed_json_handler(request: Request, exc: json.JSONDecodeError) -> JSONResponse:
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
    app.add_exception_handler(json.JSONDecodeError, malformed_json_handler)
