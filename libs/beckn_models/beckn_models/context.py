"""
Beckn v2.0.0 transport envelope models.

The context is the stable transport layer that wraps every Beckn message.
It handles identity (bapId/bppId), routing (bapUri/bppUri), and message
tracking (transactionId/messageId).

Reference: protocol-specifications-v2/api/v2.0.0/beckn.yaml
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class BecknContext(BaseModel):
    """Transport envelope for every Beckn v2 message."""

    networkId: str = "beckn.one/testnet"
    action: str
    version: str = "2.0.0"
    bapId: str
    bapUri: str
    bppId: Optional[str] = None
    bppUri: Optional[str] = None
    transactionId: str
    messageId: str
    timestamp: str
    ttl: str = "PT30S"
    schemaContext: Optional[list[str]] = None

    model_config = {"extra": "allow"}


class BecknAck(BaseModel):
    """Synchronous ACK/NACK response."""

    status: str = "ACK"


class AckMessage(BaseModel):
    ack: BecknAck = Field(default_factory=BecknAck)


class AckResponse(BaseModel):
    """Standard ACK response body."""

    message: AckMessage = Field(default_factory=AckMessage)


class BecknRequest(BaseModel):
    """Generic incoming Beckn request (context + message)."""

    context: BecknContext
    message: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


def ack_response() -> dict:
    """Return a standard ACK dict ready for JSONResponse."""
    return {"message": {"ack": {"status": "ACK"}}}


def nack_response(error_code: str, error_message: str) -> dict:
    """Return a NACK dict with error details."""
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"code": error_code, "message": error_message},
    }
