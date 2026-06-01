"""Integration tests for the admission queue (Epics A + C).

Drives the FastAPI app through ASGITransport. ``app.admission.repository``
is replaced with an in-memory fake here; ``app.registry.repository`` is
already faked by the autouse ``fake_subscribers`` fixture in conftest, so
creating an admission request also creates a parked subscriber in that
same store, letting us assert cross-table effects.
"""
from __future__ import annotations

import base64

import pytest

# A valid Ed25519 public key is exactly 32 bytes → base64. Any 32-byte blob
# passes our length-based validation (we don't verify curve membership).
VALID_KEY = base64.b64encode(b"\x01" * 32).decode()
SHORT_KEY = base64.b64encode(b"\x01" * 16).decode()


@pytest.fixture(autouse=True)
def fake_admission_store(monkeypatch):
    """In-memory replacement for ``app.admission.repository``."""
    requests: dict[int, dict] = {}
    audit: list[dict] = []
    conformance: dict[str, dict] = {}  # subscriber_id -> latest run
    next_id = [1]

    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def _create_request(*, subscriber_id, submitted_by_email, organization_data):
        rid = next_id[0]
        next_id[0] += 1
        row = {
            "id": rid,
            "subscriber_id": subscriber_id,
            "submitted_by_email": submitted_by_email,
            "organization_data": organization_data or {},
            "requested_at": _now(),
            "reviewed_at": None,
            "reviewed_by": None,
            "decision": "pending",
            "decision_reason": None,
        }
        requests[rid] = row
        return dict(row)

    async def _get_request(request_id):
        row = requests.get(request_id)
        return dict(row) if row else None

    async def _list_requests(decision=None):
        rows = list(requests.values())
        if decision:
            rows = [r for r in rows if r["decision"] == decision]
        return [dict(r) for r in rows]

    async def _set_decision(request_id, *, decision, reviewed_by, decision_reason):
        row = requests.get(request_id)
        if not row:
            return None
        row.update({
            "decision": decision,
            "reviewed_by": reviewed_by,
            "decision_reason": decision_reason,
            "reviewed_at": _now(),
        })
        return dict(row)

    async def _record_audit(*, subscriber_id, action, actor="system", details=None):
        audit.append({
            "subscriber_id": subscriber_id, "action": action,
            "actor": actor, "details": details or {},
        })

    async def _latest_conformance_run(subscriber_id):
        run = conformance.get(subscriber_id)
        return dict(run) if run else None

    from app.admission import repository
    monkeypatch.setattr(repository, "create_request", _create_request)
    monkeypatch.setattr(repository, "get_request", _get_request)
    monkeypatch.setattr(repository, "list_requests", _list_requests)
    monkeypatch.setattr(repository, "set_decision", _set_decision)
    monkeypatch.setattr(repository, "record_audit", _record_audit)
    monkeypatch.setattr(repository, "latest_conformance_run", _latest_conformance_run)

    # Never hit the real conformance kit during these tests.
    async def _noop_trigger(subscriber_id):
        return None
    from app.admission import service
    monkeypatch.setattr(service, "trigger_conformance", _noop_trigger)

    yield {"requests": requests, "audit": audit, "conformance": conformance}


def _seed_passing_conformance(store, subscriber_id, *, must_passed=True):
    store["conformance"][subscriber_id] = {
        "id": 1, "subscriber_id": subscriber_id,
        "started_at": "2026-06-01T00:00:00Z", "finished_at": "2026-06-01T00:00:05Z",
        "total_tests": 11, "passed_tests": 11 if must_passed else 7,
        "must_passed": must_passed, "should_passed": True, "results": [],
    }


def _body(**over):
    base = {
        "subscriber_id": "bpp-acme.example.com",
        "endpoint_url": "http://onix-acme:8084/bpp/receiver",
        "public_key": VALID_KEY,
        "organization": {"name": "Acme AI Providers"},
        "jurisdiction": "USA",
        "contact_email": "ops@acme.ai",
        "backend_health_url": "http://acme-bpp:3002",
    }
    base.update(over)
    return base


# ── POST /registry/admission-requests (Epic A) ──────────────────────


class TestSubmitAdmissionRequest:
    async def test_returns_202_with_request_id(self, client):
        resp = await client.post("/registry/admission-requests", json=_body())
        assert resp.status_code == 202
        data = resp.json()
        assert data["id"] >= 1
        assert data["subscriber_id"] == "bpp-acme.example.com"
        assert data["decision"] == "pending"

    async def test_creates_parked_subscriber(self, client, fake_subscribers):
        await client.post("/registry/admission-requests", json=_body())
        # fake_subscribers yields the registry store dict
        row = fake_subscribers["bpp-acme.example.com"]
        assert row["status"] == "pending_admission"

    async def test_get_parked_subscriber_does_not_500(self, client):
        """Regression: the Subscriber response model must accept the new
        admission statuses, else GET/LIST 500 on a pending_admission row."""
        await client.post("/registry/admission-requests", json=_body())
        resp = await client.get("/registry/subscribers/bpp-acme.example.com")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_admission"

    async def test_duplicate_subscriber_returns_409(self, client):
        resp = await client.post("/registry/admission-requests",
                                 json=_body(subscriber_id="bpp.example.com"))
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "subscriber_already_exists"

    async def test_malformed_public_key_returns_422(self, client):
        resp = await client.post("/registry/admission-requests",
                                 json=_body(public_key="not-base64!!!"))
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "invalid_public_key"

    async def test_wrong_length_key_returns_422(self, client):
        resp = await client.post("/registry/admission-requests",
                                 json=_body(public_key=SHORT_KEY))
        assert resp.status_code == 422

    async def test_writes_admission_requested_audit(self, client, fake_admission_store):
        await client.post("/registry/admission-requests", json=_body())
        actions = [a["action"] for a in fake_admission_store["audit"]]
        assert "admission_requested" in actions

    async def test_missing_public_key_returns_422(self, client):
        body = _body()
        del body["public_key"]
        resp = await client.post("/registry/admission-requests", json=body)
        assert resp.status_code == 422


# ── GET list / detail ───────────────────────────────────────────────


class TestListAndDetail:
    async def test_list_returns_created(self, client):
        await client.post("/registry/admission-requests", json=_body())
        resp = await client.get("/registry/admission-requests")
        assert resp.status_code == 200
        ids = {r["subscriber_id"] for r in resp.json()}
        assert "bpp-acme.example.com" in ids

    async def test_filter_by_decision_pending(self, client):
        await client.post("/registry/admission-requests", json=_body())
        resp = await client.get("/registry/admission-requests?decision=pending")
        assert all(r["decision"] == "pending" for r in resp.json())

    async def test_detail_includes_subscriber_status(self, client):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        resp = await client.get(f"/registry/admission-requests/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["subscriber_status"] == "pending_admission"

    async def test_detail_unknown_returns_404(self, client):
        resp = await client.get("/registry/admission-requests/9999")
        assert resp.status_code == 404


# ── Approve / Reject (Epic C) ───────────────────────────────────────


class TestApprove:
    async def test_approve_requires_passing_conformance(self, client, fake_admission_store):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        # no conformance run seeded → must fail
        resp = await client.post(f"/registry/admission-requests/{created['id']}/approve")
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "conformance_not_passed"

    async def test_approve_rejected_when_must_failed(self, client, fake_admission_store):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        _seed_passing_conformance(fake_admission_store, "bpp-acme.example.com",
                                  must_passed=False)
        resp = await client.post(f"/registry/admission-requests/{created['id']}/approve")
        assert resp.status_code == 422

    async def test_approve_flips_subscriber_active(self, client, fake_admission_store,
                                                   fake_subscribers):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        _seed_passing_conformance(fake_admission_store, "bpp-acme.example.com")
        resp = await client.post(f"/registry/admission-requests/{created['id']}/approve")
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approved"
        assert fake_subscribers["bpp-acme.example.com"]["status"] == "active"

    async def test_double_approve_returns_409(self, client, fake_admission_store):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        _seed_passing_conformance(fake_admission_store, "bpp-acme.example.com")
        await client.post(f"/registry/admission-requests/{created['id']}/approve")
        resp = await client.post(f"/registry/admission-requests/{created['id']}/approve")
        assert resp.status_code == 409


class TestReject:
    async def test_reject_flips_subscriber_rejected(self, client, fake_subscribers):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        resp = await client.post(
            f"/registry/admission-requests/{created['id']}/reject",
            json={"reason": "endpoint unreachable"},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "rejected"
        assert fake_subscribers["bpp-acme.example.com"]["status"] == "rejected"

    async def test_reject_requires_reason(self, client):
        created = (await client.post("/registry/admission-requests", json=_body())).json()
        resp = await client.post(
            f"/registry/admission-requests/{created['id']}/reject", json={},
        )
        assert resp.status_code == 422
