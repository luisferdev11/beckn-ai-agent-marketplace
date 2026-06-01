"""Pydantic models for the admission queue HTTP surface.

The DB schema (``infra/db/mocknet/migrations/005_admission_and_probes.sql``)
is the source of truth; these models validate inbound HTTP and shape
outbound responses.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AdmissionDecision = Literal["pending", "approved", "rejected"]


class AdmissionRequestCreate(BaseModel):
    """Body for ``POST /registry/admission-requests``.

    A self-registering partner BPP declares who they are and where their
    Beckn receiver + backend live. ``public_key`` must be a base64-encoded
    Ed25519 key (32 raw bytes) — validated in the service layer so we can
    return a precise 422.

    ``backend_health_url`` is the BPP's own HTTP base URL (NOT the ONIX
    receiver). The conformance kit and liveness probe hit it directly;
    when omitted, conformance cannot run and the request stays pending.
    """
    model_config = ConfigDict(extra="forbid")

    subscriber_id: str = Field(..., min_length=1, max_length=255)
    endpoint_url: str = Field(..., min_length=1)
    public_key: str = Field(..., min_length=1)
    organization: dict = Field(default_factory=dict)
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    backend_health_url: Optional[str] = None
    role: Literal["BPP"] = "BPP"


class RejectBody(BaseModel):
    """Body for ``POST /registry/admission-requests/{id}/reject``."""
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=2000)


class ApproveBody(BaseModel):
    """Optional body for ``.../approve`` — who approved, for the audit log."""
    model_config = ConfigDict(extra="forbid")

    reviewed_by: Optional[str] = Field(default=None, max_length=255)


class ConformanceSummary(BaseModel):
    """Latest conformance run, embedded in admission request detail."""
    model_config = ConfigDict(extra="ignore")

    id: int
    started_at: str
    finished_at: Optional[str] = None
    total_tests: int
    passed_tests: int
    must_passed: Optional[bool] = None
    should_passed: Optional[bool] = None
    results: list = Field(default_factory=list)


class AdmissionRequest(BaseModel):
    """Read shape returned by the admission routes."""
    model_config = ConfigDict(extra="ignore")

    id: int
    subscriber_id: str
    submitted_by_email: Optional[str] = None
    organization_data: dict = Field(default_factory=dict)
    requested_at: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    decision: AdmissionDecision
    decision_reason: Optional[str] = None


class AdmissionRequestDetail(AdmissionRequest):
    """Admission request enriched with the subscriber's latest conformance
    run and current status — what the admin drawer needs (Epic C2)."""

    subscriber_status: Optional[str] = None
    latest_conformance: Optional[ConformanceSummary] = None
