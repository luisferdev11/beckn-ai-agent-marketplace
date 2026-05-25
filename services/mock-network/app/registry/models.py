"""Pydantic models for the Registry API surface.

The DB schema is the source of truth (see ``infra/db/mocknet/migrations``).
These models exist only to validate inbound HTTP and to shape outbound
responses; they intentionally mirror the table columns 1:1 so adding a
column is a single-place change here.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SubscriberRole = Literal["BAP", "BPP", "CDS", "DS"]
SubscriberStatus = Literal["pending_kyc", "active", "suspended", "deprecated"]
SubscriberHealth = Literal["unknown", "healthy", "degraded", "down"]


class SubscriberCreate(BaseModel):
    """Body for ``POST /registry/subscribers``.

    Note: ``status`` and ``health`` are not accepted on create — new rows
    always start at ``status='active'`` (MVP has no KYC flow) and
    ``health='unknown'`` (the probe will update it).

    ``backend_health_url`` is optional: when set, the liveness probe hits
    it directly; when omitted, the probe falls back to deriving a URL
    from ``endpoint_url`` (which often fails because ONIX does not expose
    /health).
    """
    model_config = ConfigDict(extra="forbid")

    subscriber_id: str = Field(..., min_length=1, max_length=255)
    role: SubscriberRole
    endpoint_url: str = Field(..., min_length=1)
    public_key: Optional[str] = None
    organization: Optional[dict] = None
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    backend_health_url: Optional[str] = None


class SubscriberUpdate(BaseModel):
    """Body for ``PATCH /registry/subscribers/{id}`` — partial update.

    ``health``, ``last_seen_at``, ``consecutive_failures`` are owned by the
    liveness probe and cannot be set through this endpoint.
    """
    model_config = ConfigDict(extra="forbid")

    status: Optional[SubscriberStatus] = None
    organization: Optional[dict] = None
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    kyc_data: Optional[dict] = None
    endpoint_url: Optional[str] = None
    public_key: Optional[str] = None
    backend_health_url: Optional[str] = None


class Subscriber(BaseModel):
    """Read shape returned by every route."""
    model_config = ConfigDict(extra="ignore")

    id: int
    subscriber_id: str
    role: SubscriberRole
    endpoint_url: str
    backend_health_url: Optional[str] = None
    public_key: Optional[str] = None
    organization: dict
    jurisdiction: Optional[str] = None
    status: SubscriberStatus
    health: SubscriberHealth
    last_seen_at: Optional[str] = None
    consecutive_failures: int = 0
    kyc_data: dict
    registered_at: str
    updated_at: str
