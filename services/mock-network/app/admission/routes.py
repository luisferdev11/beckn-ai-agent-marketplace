"""Admission queue HTTP surface.

No auth in this MVP (same posture as ``app.registry.routes``): these
endpoints assume an internal network boundary. The admin-only operations
(approve/reject) must sit behind a gateway that enforces the ``admin``
role before this is exposed publicly.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.admission import service
from app.admission.models import (
    AdmissionRequest,
    AdmissionRequestCreate,
    AdmissionRequestDetail,
    ApproveBody,
    RejectBody,
)
from app.admission.service import (
    AlreadyReviewed,
    ConformanceNotPassed,
    InvalidPublicKey,
    RequestNotFound,
)
from app.registry.service import SubscriberAlreadyExists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registry/admission-requests", tags=["admission"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AdmissionRequest)
async def submit_admission_request(
    payload: AdmissionRequestCreate,
    background: BackgroundTasks,
) -> AdmissionRequest:
    """A partner BPP self-registers. Returns 202 + the request row; the
    conformance kit runs asynchronously against the declared backend."""
    try:
        request = await service.create_admission(payload.model_dump(exclude_none=True))
    except InvalidPublicKey as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_public_key", "message": str(exc)},
        )
    except SubscriberAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "subscriber_already_exists",
                    "subscriber_id": payload.subscriber_id},
        )

    # Auto-trigger conformance (Epic B2). Only meaningful if the BPP gave us
    # a backend URL to probe; the runner records a failed run otherwise.
    background.add_task(service.trigger_conformance, payload.subscriber_id)
    return AdmissionRequest(**request)


@router.get("", response_model=list[AdmissionRequest])
async def list_admission_requests(
    decision: Optional[str] = None,
) -> list[AdmissionRequest]:
    rows = await service.list_requests(decision=decision)
    return [AdmissionRequest(**r) for r in rows]


@router.get("/{request_id}", response_model=AdmissionRequestDetail)
async def get_admission_request(request_id: int) -> AdmissionRequestDetail:
    try:
        detail = await service.get_detail(request_id)
    except RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "admission_request_not_found", "request_id": request_id},
        )
    return AdmissionRequestDetail(**detail)


@router.post("/{request_id}/approve", response_model=AdmissionRequest)
async def approve_admission_request(
    request_id: int, payload: Optional[ApproveBody] = None,
) -> AdmissionRequest:
    reviewed_by = payload.reviewed_by if payload else None
    try:
        updated = await service.approve(request_id, reviewed_by=reviewed_by)
    except RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "admission_request_not_found", "request_id": request_id},
        )
    except AlreadyReviewed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "already_reviewed", "decision": str(exc)},
        )
    except ConformanceNotPassed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "conformance_not_passed", "message": exc.reason},
        )
    logger.info("admission: %s approved", request_id)
    return AdmissionRequest(**updated)


@router.post("/{request_id}/reject", response_model=AdmissionRequest)
async def reject_admission_request(
    request_id: int, payload: RejectBody,
) -> AdmissionRequest:
    try:
        updated = await service.reject(
            request_id, reason=payload.reason, reviewed_by=None,
        )
    except RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "admission_request_not_found", "request_id": request_id},
        )
    except AlreadyReviewed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "already_reviewed", "decision": str(exc)},
        )
    logger.info("admission: %s rejected", request_id)
    return AdmissionRequest(**updated)


@router.post("/{request_id}/retry-conformance",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=AdmissionRequest)
async def retry_conformance(
    request_id: int, background: BackgroundTasks,
) -> AdmissionRequest:
    """Re-run the conformance kit for a pending request (Epic B4)."""
    try:
        detail = await service.get_detail(request_id)
    except RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "admission_request_not_found", "request_id": request_id},
        )
    background.add_task(service.trigger_conformance, detail["subscriber_id"])
    return AdmissionRequest(**{k: detail[k] for k in AdmissionRequest.model_fields})
