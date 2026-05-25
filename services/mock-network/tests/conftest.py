"""Mock-network test fixtures.

The Registry repository normally talks to ``postgres-mocknet`` via asyncpg.
For unit and integration tests we replace each repository function with an
in-memory implementation so the suite is fast and runnable offline. Real DB
behaviour is exercised by an explicit smoke against the live container.

Fixtures provided:

  app                FastAPI app from ``app.main``. Lifespan is intentionally
                     NOT triggered by AsyncClient/ASGITransport defaults so
                     the real pool never opens.

  client             httpx AsyncClient bound to the app.

  fake_subscribers   Autouse fixture. Seeds the in-memory store with the
                     three identities the migration also seeds and patches
                     ``app.registry.repository`` to read/write from it.
                     Yields the dict so tests can introspect.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _seed_rows() -> dict[str, dict]:
    """Same three identities the SQL migration seeds. Kept in sync by hand."""
    return {
        "bap.example.com": {
            "id": 1,
            "subscriber_id": "bap.example.com",
            "role": "BAP",
            "endpoint_url": "http://onix-bap:8081/bap/receiver",
            "backend_health_url": "http://bap-marketplace:3001",
            "public_key": "g/3swjI93IhZ0SScrVZapeLjU+W0AeiSid3LViYZJFo=",
            "organization": {"name": "Demo Buyer Marketplace", "shortDesc": "Reference BAP"},
            "jurisdiction": "IND",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        "bpp.example.com": {
            "id": 2,
            "subscriber_id": "bpp.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp:8082/bpp/receiver",
            "backend_health_url": "http://bpp-provider:3002",
            "public_key": "CqVy97DW45bcZPPrWIYGe2ldl9C93NFeVciiAEYsvR0=",
            "organization": {"name": "General Tecla Industries", "shortDesc": "Demo provider"},
            "jurisdiction": "IND",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        "bpp-serg.example.com": {
            "id": 3,
            "subscriber_id": "bpp-serg.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp-serg:8083/bpp/receiver",
            "backend_health_url": "http://bpp-serg:3005",
            "public_key": "bfbdo3TxLzSRutUMSjl+OeDtZgqVDlCuLbR2aDbtPN0=",
            "organization": {"name": "Serg Ops", "shortDesc": "Second demo provider"},
            "jurisdiction": "MEX",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    }


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def fake_subscribers(monkeypatch):
    """In-memory replacement for ``app.registry.repository``."""
    store: dict[str, dict] = _seed_rows()
    next_id = [max(row["id"] for row in store.values()) + 1] if store else [1]

    async def _create(data: dict) -> dict:
        sid = data["subscriber_id"]
        if sid in store:
            raise ValueError(f"subscriber {sid} already exists")
        row = {
            "id": next_id[0],
            "subscriber_id": sid,
            "role": data["role"],
            "endpoint_url": data["endpoint_url"],
            "backend_health_url": data.get("backend_health_url"),
            "public_key": data.get("public_key"),
            "organization": data.get("organization") or {},
            "jurisdiction": data.get("jurisdiction"),
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        store[sid] = row
        next_id[0] += 1
        return dict(row)

    async def _get(subscriber_id: str) -> Optional[dict]:
        row = store.get(subscriber_id)
        return dict(row) if row else None

    async def _list(role: Optional[str] = None, status_filter: Optional[str] = None) -> list[dict]:
        rows = list(store.values())
        if role:
            rows = [r for r in rows if r["role"] == role]
        if status_filter:
            rows = [r for r in rows if r["status"] == status_filter]
        return [dict(r) for r in rows]

    async def _update(subscriber_id: str, **fields) -> Optional[dict]:
        row = store.get(subscriber_id)
        if not row:
            return None
        for k, v in fields.items():
            if v is not None:
                row[k] = v
        row["updated_at"] = _now_iso()
        return dict(row)

    async def _deactivate(subscriber_id: str) -> Optional[dict]:
        return await _update(subscriber_id, status="deprecated")

    async def _update_health(
        subscriber_id: str,
        *,
        health: str,
        last_seen_at: Optional[str],
        consecutive_failures: int,
    ) -> None:
        row = store.get(subscriber_id)
        if not row:
            return
        row["health"] = health
        row["last_seen_at"] = last_seen_at
        row["consecutive_failures"] = consecutive_failures
        row["updated_at"] = _now_iso()

    from app.registry import repository
    monkeypatch.setattr(repository, "create_subscriber", _create)
    monkeypatch.setattr(repository, "get_subscriber", _get)
    monkeypatch.setattr(repository, "list_subscribers", _list)
    monkeypatch.setattr(repository, "update_subscriber", _update)
    monkeypatch.setattr(repository, "deactivate_subscriber", _deactivate)
    monkeypatch.setattr(repository, "update_health", _update_health)

    yield store

    store.clear()
