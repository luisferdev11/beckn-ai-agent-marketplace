"""Registry business logic — the only layer that knows the difference
between "a duplicate id" and an HTTP status code.

Routes call into here; the repository sits below. Keeping HTTP-aware
errors out of the repository means we can later add other surfaces
(gRPC, an internal Python API) without rewriting business rules.
"""
from __future__ import annotations

from typing import Optional

from app.registry import repository


class SubscriberAlreadyExists(Exception):
    """Raised when create() hits a unique constraint on subscriber_id."""


class SubscriberNotFound(Exception):
    """Raised when an operation references a subscriber_id that does not
    exist. The route layer translates this to HTTP 404."""


async def create(data: dict) -> dict:
    existing = await repository.get_subscriber(data["subscriber_id"])
    if existing is not None:
        raise SubscriberAlreadyExists(data["subscriber_id"])
    try:
        return await repository.create_subscriber(data)
    except ValueError:
        # Fake-repo signal used by the test conftest.
        raise SubscriberAlreadyExists(data["subscriber_id"])
    except Exception as exc:  # asyncpg.UniqueViolationError in prod
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise SubscriberAlreadyExists(data["subscriber_id"]) from exc
        raise


async def get(subscriber_id: str) -> dict:
    row = await repository.get_subscriber(subscriber_id)
    if row is None:
        raise SubscriberNotFound(subscriber_id)
    return row


async def list_all(
    role: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> list[dict]:
    return await repository.list_subscribers(role=role, status_filter=status_filter)


async def update(subscriber_id: str, fields: dict) -> dict:
    row = await repository.update_subscriber(subscriber_id, **fields)
    if row is None:
        raise SubscriberNotFound(subscriber_id)
    return row


async def deactivate(subscriber_id: str) -> dict:
    row = await repository.deactivate_subscriber(subscriber_id)
    if row is None:
        raise SubscriberNotFound(subscriber_id)
    return row
