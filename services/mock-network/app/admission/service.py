"""Admission business logic — the state machine that takes a partner BPP
from self-registration to ``active``.

Flow (docs/PLAN-BPP-REGISTRY-LIFECYCLE.md Epics A/B/C):

    POST /admission-requests
        → validate Ed25519 public_key            (else InvalidPublicKey → 422)
        → subscriber must not already exist       (else SubscriberAlreadyExists → 409)
        → create subscriber status=pending_admission
        → create admission_requests row
        → audit 'admission_requested'
        → (background) run conformance kit, persist conformance_runs

    POST /admission-requests/{id}/approve
        → latest conformance must have must_passed=true (else ConformanceNotPassed → 422)
        → subscriber status=active, decision=approved, audit 'approved'

    POST /admission-requests/{id}/reject
        → subscriber status=rejected, decision=rejected, audit 'rejected'

HTTP-status concerns live in the route layer; this module raises domain
exceptions only.
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Optional

from app.admission import repository
from app.registry import repository as registry_repository
from app.registry.service import SubscriberAlreadyExists

logger = logging.getLogger(__name__)

ED25519_KEY_LEN = 32


class InvalidPublicKey(Exception):
    """Raised when ``public_key`` is not base64-encoded 32-byte Ed25519."""


class RequestNotFound(Exception):
    """Raised when an admission request id does not exist (→ 404)."""


class AlreadyReviewed(Exception):
    """Raised when approving/rejecting a request that is not pending (→ 409)."""


class ConformanceNotPassed(Exception):
    """Raised when approving a BPP whose latest conformance run did not pass
    the 'must' tier (→ 422). Carries a human-readable reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_ed25519_b64(public_key: str) -> None:
    """Raise ``InvalidPublicKey`` unless ``public_key`` decodes to exactly
    32 bytes from base64. We do not verify the point is on the curve —
    that needs a crypto lib we deliberately keep out of this service — but
    the length check rejects the overwhelmingly common copy-paste errors.
    """
    try:
        raw = base64.b64decode(public_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPublicKey(f"public_key is not valid base64: {exc}") from exc
    if len(raw) != ED25519_KEY_LEN:
        raise InvalidPublicKey(
            f"public_key decodes to {len(raw)} bytes; "
            f"Ed25519 requires {ED25519_KEY_LEN}"
        )


# ─── Conformance auto-trigger seam ──────────────────────────────────
#
# Wired by the route layer through FastAPI BackgroundTasks. Defined as a
# module-level async function so tests can monkeypatch it without spinning
# up the real kit (which would try to HTTP the BPP). The real
# implementation lives in ``app.conformance.runner``.


async def trigger_conformance(subscriber_id: str) -> None:
    """Run the conformance kit against a subscriber and persist the run.

    Imported lazily so the admission module does not hard-depend on the
    conformance package at import time (keeps the two refactors decoupled).
    Any failure is swallowed + logged: a flaky kit run must never crash the
    background task or leave the request in a bad state.
    """
    try:
        from app.conformance import runner
    except ImportError:  # pragma: no cover — conformance module not yet wired
        logger.warning("conformance module unavailable; skipping auto-trigger for %s",
                       subscriber_id)
        return
    try:
        await runner.run_for_subscriber(subscriber_id)
    except Exception as exc:  # noqa: BLE001 — background task must not crash
        logger.warning("conformance auto-trigger failed for %s: %s", subscriber_id, exc)


# ─── Use cases ──────────────────────────────────────────────────────


async def create_admission(data: dict) -> dict:
    """Validate, park the subscriber, and open an admission request.

    Returns the created admission_requests row. The caller schedules
    ``trigger_conformance`` afterwards.
    """
    validate_ed25519_b64(data["public_key"])

    subscriber_id = data["subscriber_id"]

    # Create the parked subscriber first. ``registry.service.create`` raises
    # SubscriberAlreadyExists which the route maps to 409.
    from app.registry import service as registry_service
    await registry_service.create({
        "subscriber_id": subscriber_id,
        "role": data.get("role", "BPP"),
        "endpoint_url": data["endpoint_url"],
        "public_key": data["public_key"],
        "organization": data.get("organization") or {},
        "jurisdiction": data.get("jurisdiction"),
        "backend_health_url": data.get("backend_health_url"),
        "status": "pending_admission",
    })

    request = await repository.create_request(
        subscriber_id=subscriber_id,
        submitted_by_email=data.get("contact_email"),
        organization_data=data.get("organization") or {},
    )

    await repository.record_audit(
        subscriber_id=subscriber_id,
        action="admission_requested",
        actor=data.get("contact_email") or "self",
        details={"request_id": request["id"], "endpoint_url": data["endpoint_url"]},
    )

    logger.info("admission: request %s opened for %s", request["id"], subscriber_id)
    return request


async def get_detail(request_id: int) -> dict:
    request = await repository.get_request(request_id)
    if request is None:
        raise RequestNotFound(request_id)

    subscriber = await registry_repository.get_subscriber(request["subscriber_id"])
    conformance = await repository.latest_conformance_run(request["subscriber_id"])

    detail = dict(request)
    detail["subscriber_status"] = subscriber["status"] if subscriber else None
    detail["latest_conformance"] = conformance
    return detail


async def approve(request_id: int, *, reviewed_by: Optional[str]) -> dict:
    request = await repository.get_request(request_id)
    if request is None:
        raise RequestNotFound(request_id)
    if request["decision"] != "pending":
        raise AlreadyReviewed(request["decision"])

    subscriber_id = request["subscriber_id"]

    run = await repository.latest_conformance_run(subscriber_id)
    if run is None:
        raise ConformanceNotPassed(
            "no conformance run on record; run conformance before approving"
        )
    if not run.get("must_passed"):
        raise ConformanceNotPassed(
            "latest conformance run did not pass all 'must' tests"
        )

    await registry_repository.update_subscriber(subscriber_id, status="active")
    updated = await repository.set_decision(
        request_id, decision="approved", reviewed_by=reviewed_by, decision_reason=None,
    )
    await repository.record_audit(
        subscriber_id=subscriber_id,
        action="approved",
        actor=reviewed_by or "admin",
        details={"request_id": request_id, "conformance_run_id": run["id"]},
    )
    logger.info("admission: request %s APPROVED for %s", request_id, subscriber_id)
    return updated


async def reject(
    request_id: int, *, reason: str, reviewed_by: Optional[str],
) -> dict:
    request = await repository.get_request(request_id)
    if request is None:
        raise RequestNotFound(request_id)
    if request["decision"] != "pending":
        raise AlreadyReviewed(request["decision"])

    subscriber_id = request["subscriber_id"]

    await registry_repository.update_subscriber(subscriber_id, status="rejected")
    updated = await repository.set_decision(
        request_id, decision="rejected", reviewed_by=reviewed_by, decision_reason=reason,
    )
    await repository.record_audit(
        subscriber_id=subscriber_id,
        action="rejected",
        actor=reviewed_by or "admin",
        details={"request_id": request_id, "reason": reason},
    )
    logger.info("admission: request %s REJECTED for %s", request_id, subscriber_id)
    return updated


async def list_requests(decision: Optional[str] = None) -> list[dict]:
    return await repository.list_requests(decision=decision)
