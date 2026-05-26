"""Registry HTTP surface — admin CRUD over subscribers.

There is no auth in this MVP. The endpoints assume they live behind an
internal network boundary; production deployment must add a gateway
(Beckn signature, or simple bearer token) before exposing this.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from app.registry import service
from app.registry.models import (
    Subscriber,
    SubscriberCreate,
    SubscriberRole,
    SubscriberStatus,
    SubscriberUpdate,
)
from app.registry.service import SubscriberAlreadyExists, SubscriberNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registry/subscribers", tags=["registry"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Subscriber)
async def create_subscriber(payload: SubscriberCreate) -> Subscriber:
    try:
        row = await service.create(payload.model_dump(exclude_none=True))
    except SubscriberAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "subscriber_already_exists",
                "subscriber_id": payload.subscriber_id,
            },
        )
    logger.info("registry: created subscriber %s (%s)", row["subscriber_id"], row["role"])
    return Subscriber(**row)


@router.get("", response_model=list[Subscriber])
async def list_subscribers(
    role: Optional[SubscriberRole] = None,
    status_filter: Optional[SubscriberStatus] = None,
) -> list[Subscriber]:
    """List subscribers; optional ``role`` and ``status_filter`` query params.

    ``status_filter`` is named with a suffix to avoid shadowing the
    ``fastapi.status`` enum we import for HTTP codes.
    """
    rows = await service.list_all(role=role, status_filter=status_filter)
    return [Subscriber(**r) for r in rows]


@router.get("/{subscriber_id}", response_model=Subscriber)
async def get_subscriber(subscriber_id: str) -> Subscriber:
    try:
        row = await service.get(subscriber_id)
    except SubscriberNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "subscriber_not_found", "subscriber_id": subscriber_id},
        )
    return Subscriber(**row)


@router.patch("/{subscriber_id}", response_model=Subscriber)
async def patch_subscriber(subscriber_id: str, payload: SubscriberUpdate) -> Subscriber:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "empty_update_body"},
        )
    try:
        row = await service.update(subscriber_id, fields)
    except SubscriberNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "subscriber_not_found", "subscriber_id": subscriber_id},
        )
    logger.info("registry: updated subscriber %s (%s)",
                subscriber_id, ", ".join(fields.keys()))
    return Subscriber(**row)


@router.delete("/{subscriber_id}", response_model=Subscriber)
async def delete_subscriber(subscriber_id: str) -> Subscriber:
    """Soft-delete: marks status='deprecated'. Idempotent — calling on an
    already-deprecated subscriber returns the same row without error."""
    try:
        row = await service.deactivate(subscriber_id)
    except SubscriberNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "subscriber_not_found", "subscriber_id": subscriber_id},
        )
    logger.info("registry: deprecated subscriber %s", subscriber_id)
    return Subscriber(**row)
