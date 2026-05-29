"""Integration tests for Serg /api/webhook/rate.

Mirrors the Tecla rate handler test contract:

  - persist incoming RatingInputs (in-memory for Serg — postgres
    migration is tracked separately),
  - reject ratings for transactions Serg has never seen,
  - reject ratings whose score lies outside its declared range,
  - return a Beckn v2 ``on_rate`` envelope echoing accepted inputs.
"""
from __future__ import annotations

import uuid

import pytest


def _rate_message(*, target_id: str = "summarizer-v1", score: float = 4.5,
                  feedback: str | None = None) -> dict:
    rinput: dict = {
        "target": {
            "id": target_id,
            "descriptor": {"code": "agent", "name": "AI agent"},
        },
        "range": {"min": 1.0, "max": 5.0, "value": score},
    }
    if feedback:
        rinput["feedbackFormSubmission"] = {"data": {"review": feedback}}
    return {"ratingInputs": [rinput]}


def _rate_context(txn_id: str | None = None) -> dict:
    return {
        "networkId": "beckn.one/testnet",
        "action": "rate",
        "version": "2.0.0",
        "bapId": "bap.example.com",
        "bapUri": "http://onix-bap:8081/bap/receiver",
        "bppId": "bpp-serg.example.com",
        "bppUri": "http://onix-bpp-serg:8083/bpp/receiver",
        "transactionId": txn_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": "2026-05-27T07:00:00.000Z",
        "ttl": "PT30S",
    }


def _seed_completed_contract(*, txn_id: str, agent_id: str = "summarizer-v1") -> None:
    """Seed Serg's in-memory contract store directly so the rate handler
    sees a transaction it has previously processed."""
    from app.handlers import beckn_actions as ba
    contract_id = f"contract-{txn_id[:8]}"
    ba._contracts[contract_id] = {
        "id": contract_id,
        "transaction_id": txn_id,
        "agent_id": agent_id,
        "status": "COMPLETED",
        "commitments": [],
        "consideration": [],
        "performance": [],
        "settlements": [],
        "participants": [],
    }


@pytest.fixture(autouse=True)
def _reset_serg_state():
    """Serg's contract + rating stores are module-level globals; clear
    between tests to keep them independent."""
    from app.handlers import beckn_actions as ba
    ba._contracts.clear()
    if hasattr(ba, "_ratings_received"):
        ba._ratings_received.clear()
    yield
    ba._contracts.clear()
    if hasattr(ba, "_ratings_received"):
        ba._ratings_received.clear()


class TestRateAcceptsAndPersists:
    async def test_returns_ack(self, client):
        txn_id = "txn-serg-rate-001"
        _seed_completed_contract(txn_id=txn_id)
        resp = await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id), "message": _rate_message()},
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": {"ack": {"status": "ACK"}}}

    async def test_persists_rating(self, client):
        from app.handlers import beckn_actions as ba
        txn_id = "txn-serg-rate-002"
        _seed_completed_contract(txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context(txn_id),
                "message": _rate_message(score=4.0, feedback="bien"),
            },
        )
        records = [r for r in ba._ratings_received if r["transaction_id"] == txn_id]
        assert len(records) == 1
        assert float(records[0]["score"]) == 4.0
        assert records[0]["target_id"] == "summarizer-v1"
        assert records[0]["feedback"] == "bien"

    async def test_re_rating_upserts_no_duplicates(self, client):
        from app.handlers import beckn_actions as ba
        txn_id = "txn-serg-rate-003"
        _seed_completed_contract(txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id),
                  "message": _rate_message(score=2.0)},
        )
        await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id),
                  "message": _rate_message(score=5.0)},
        )
        records = [r for r in ba._ratings_received if r["transaction_id"] == txn_id]
        assert len(records) == 1
        assert float(records[0]["score"]) == 5.0


class TestRateRejectsOrphan:
    async def test_unknown_txn_does_not_persist(self, client):
        from app.handlers import beckn_actions as ba
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context("txn-serg-rate-orphan"),
                "message": _rate_message(),
            },
        )
        assert ba._ratings_received == []


class TestRateInvalidPayload:
    async def test_out_of_range_does_not_persist(self, client):
        from app.handlers import beckn_actions as ba
        txn_id = "txn-serg-rate-bad-001"
        _seed_completed_contract(txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context(txn_id),
                "message": _rate_message(score=42.0),
            },
        )
        assert ba._ratings_received == []
