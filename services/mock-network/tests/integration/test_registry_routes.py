"""Integration tests for the Registry HTTP surface.

Drives the FastAPI app through ASGITransport with the repository
monkeypatched to an in-memory fake (see ``conftest.fake_subscribers``).
Three subscribers are pre-seeded (BAP + 2 BPPs) matching the SQL
migration; tests assume they exist.
"""
from __future__ import annotations

import pytest


# ── POST /registry/subscribers ──────────────────────────────────────


class TestCreateSubscriber:
    async def test_creates_with_minimal_body_returns_201(self, client):
        body = {
            "subscriber_id": "bpp-new.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp-new:8084/bpp/receiver",
        }
        resp = await client.post("/registry/subscribers", json=body)
        assert resp.status_code == 201

    async def test_response_echoes_input_fields(self, client):
        body = {
            "subscriber_id": "bpp-new.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp-new:8084/bpp/receiver",
            "jurisdiction": "USA",
            "organization": {"name": "Acme AI"},
        }
        resp = await client.post("/registry/subscribers", json=body)
        data = resp.json()
        assert data["subscriber_id"] == "bpp-new.example.com"
        assert data["role"] == "BPP"
        assert data["endpoint_url"] == "http://onix-bpp-new:8084/bpp/receiver"
        assert data["jurisdiction"] == "USA"
        assert data["organization"] == {"name": "Acme AI"}

    async def test_new_subscriber_defaults_status_active(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "x.example.com",
            "role": "BPP",
            "endpoint_url": "http://x",
        })
        assert resp.json()["status"] == "active"

    async def test_new_subscriber_defaults_health_unknown(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "x.example.com",
            "role": "BPP",
            "endpoint_url": "http://x",
        })
        assert resp.json()["health"] == "unknown"

    async def test_duplicate_subscriber_id_returns_409(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "bpp.example.com",  # already seeded
            "role": "BPP",
            "endpoint_url": "http://x",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "subscriber_already_exists"

    async def test_invalid_role_returns_422(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "x.example.com",
            "role": "INVALID",
            "endpoint_url": "http://x",
        })
        assert resp.status_code == 422

    async def test_missing_required_field_returns_422(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "x.example.com",
            "role": "BPP",
            # missing endpoint_url
        })
        assert resp.status_code == 422

    async def test_unknown_field_is_rejected(self, client):
        resp = await client.post("/registry/subscribers", json={
            "subscriber_id": "x.example.com",
            "role": "BPP",
            "endpoint_url": "http://x",
            "status": "active",  # not allowed on create
        })
        assert resp.status_code == 422


# ── GET /registry/subscribers ───────────────────────────────────────


class TestListSubscribers:
    async def test_returns_seeded_three(self, client):
        resp = await client.get("/registry/subscribers")
        assert resp.status_code == 200
        rows = resp.json()
        ids = {r["subscriber_id"] for r in rows}
        assert ids >= {"bap.example.com", "bpp.example.com", "bpp-serg.example.com"}

    async def test_filter_by_role_bpp(self, client):
        resp = await client.get("/registry/subscribers?role=BPP")
        rows = resp.json()
        assert all(r["role"] == "BPP" for r in rows)
        assert len(rows) >= 2

    async def test_filter_by_role_bap(self, client):
        resp = await client.get("/registry/subscribers?role=BAP")
        rows = resp.json()
        assert all(r["role"] == "BAP" for r in rows)
        assert len(rows) >= 1

    async def test_filter_by_status_active(self, client):
        resp = await client.get("/registry/subscribers?status_filter=active")
        rows = resp.json()
        assert all(r["status"] == "active" for r in rows)

    async def test_filter_by_status_deprecated_initially_empty(self, client):
        resp = await client.get("/registry/subscribers?status_filter=deprecated")
        assert resp.json() == []

    async def test_invalid_role_filter_rejected(self, client):
        resp = await client.get("/registry/subscribers?role=PIRATE")
        assert resp.status_code == 422


# ── GET /registry/subscribers/{id} ──────────────────────────────────


class TestGetSubscriber:
    async def test_known_id_returns_full_record(self, client):
        resp = await client.get("/registry/subscribers/bpp.example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscriber_id"] == "bpp.example.com"
        assert data["role"] == "BPP"
        assert data["status"] == "active"

    async def test_unknown_id_returns_404(self, client):
        resp = await client.get("/registry/subscribers/ghost.example.com")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "subscriber_not_found"


# ── PATCH /registry/subscribers/{id} ────────────────────────────────


class TestPatchSubscriber:
    async def test_update_status_to_suspended(self, client):
        resp = await client.patch(
            "/registry/subscribers/bpp.example.com",
            json={"status": "suspended"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

    async def test_update_persists_across_get(self, client):
        await client.patch(
            "/registry/subscribers/bpp.example.com",
            json={"jurisdiction": "USA"},
        )
        got = await client.get("/registry/subscribers/bpp.example.com")
        assert got.json()["jurisdiction"] == "USA"

    async def test_update_unknown_id_returns_404(self, client):
        resp = await client.patch(
            "/registry/subscribers/ghost.example.com",
            json={"status": "suspended"},
        )
        assert resp.status_code == 404

    async def test_empty_body_returns_400(self, client):
        resp = await client.patch(
            "/registry/subscribers/bpp.example.com",
            json={},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "empty_update_body"

    async def test_invalid_status_returns_422(self, client):
        resp = await client.patch(
            "/registry/subscribers/bpp.example.com",
            json={"status": "destroyed"},
        )
        assert resp.status_code == 422

    async def test_cannot_update_health_field(self, client):
        """health is owned by the liveness probe — not mutable via PATCH."""
        resp = await client.patch(
            "/registry/subscribers/bpp.example.com",
            json={"health": "healthy"},
        )
        assert resp.status_code == 422


# ── DELETE /registry/subscribers/{id} ───────────────────────────────


class TestDeleteSubscriber:
    async def test_soft_deletes_to_deprecated(self, client):
        resp = await client.delete("/registry/subscribers/bpp.example.com")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

    async def test_deprecated_subscriber_still_retrievable(self, client):
        await client.delete("/registry/subscribers/bpp.example.com")
        got = await client.get("/registry/subscribers/bpp.example.com")
        assert got.status_code == 200
        assert got.json()["status"] == "deprecated"

    async def test_delete_unknown_id_returns_404(self, client):
        resp = await client.delete("/registry/subscribers/ghost.example.com")
        assert resp.status_code == 404

    async def test_delete_is_idempotent(self, client):
        first = await client.delete("/registry/subscribers/bpp.example.com")
        second = await client.delete("/registry/subscribers/bpp.example.com")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "deprecated"
