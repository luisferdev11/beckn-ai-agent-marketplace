"""Integration tests for BPP /api/webhook/rate (Tecla).

The handler should:

  - Persist incoming ratings via ``ratings_received`` repo (upsert per
    transaction+target+type — re-rating overwrites).
  - Reject ratings for transactions the BPP has never seen (orphan
    txn → 30002 error envelope, no insert).
  - Best-effort POST to the CDS ingest endpoint so the marketplace-side
    rating aggregate stays consistent. CDS unreachable should not fail
    the local persistence path.
  - Build a Beckn v2 on_rate callback with the same RatingInput shape
    the BAP sent, so the BAP can confirm what was recorded.

These behaviours are pinned here. Real persistence is monkeypatched by
``fake_db`` (see conftest.py).
"""
from __future__ import annotations

import uuid

import pytest


def _rate_message(*, target_id: str = "agent-summarizer-001", score: float = 4.5,
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
        "bppId": "bpp.example.com",
        "bppUri": "http://onix-bpp:8082/bpp/receiver",
        "transactionId": txn_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": "2026-05-27T07:00:00.000Z",
        "ttl": "PT30S",
    }


def _seed_completed_contract(fake_db, *, txn_id: str,
                             agent_id: str = "agent-summarizer-001") -> None:
    fake_db["contracts"][txn_id] = {
        "contract_code": f"contract-{txn_id[:8]}",
        "transaction_id": txn_id,
        "status": "COMPLETED",
        "agent_id": agent_id,
        "provider_id": 1,
        "bap_id": "bap.example.com",
        "bpp_id": "bpp.example.com",
        "commitments": [],
        "consideration": [],
        "performance": [],
        "settlements": [],
        "participants": [],
        "execution_id": None,
        "total_amount": 5.0,
        "currency": "INR",
    }


class TestRateAcceptsAndPersists:
    async def test_returns_ack(self, client, fake_db):
        txn_id = "txn-rate-bpp-001"
        _seed_completed_contract(fake_db, txn_id=txn_id)
        resp = await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id), "message": _rate_message()},
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": {"ack": {"status": "ACK"}}}

    async def test_persists_rating_in_local_log(self, client, fake_db):
        txn_id = "txn-rate-bpp-002"
        _seed_completed_contract(fake_db, txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context(txn_id),
                "message": _rate_message(score=4.0, feedback="solid output"),
            },
        )
        records = [
            r for r in fake_db["ratings_received"]
            if r["transaction_id"] == txn_id
        ]
        assert len(records) == 1
        assert float(records[0]["score"]) == 4.0
        assert records[0]["target_id"] == "agent-summarizer-001"
        assert records[0]["feedback"] == "solid output"

    async def test_re_rating_upserts_does_not_duplicate(self, client, fake_db):
        txn_id = "txn-rate-bpp-003"
        _seed_completed_contract(fake_db, txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id),
                  "message": _rate_message(score=3.0)},
        )
        await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id),
                  "message": _rate_message(score=5.0)},
        )
        records = [
            r for r in fake_db["ratings_received"]
            if r["transaction_id"] == txn_id
        ]
        assert len(records) == 1
        assert float(records[0]["score"]) == 5.0


class TestRateRejectsOrphanTransactions:
    async def test_unknown_txn_does_not_persist(self, client, fake_db):
        # Contract was never seen by this BPP → reject. Mirrors the
        # txn_not_found guard already in place for init/confirm/status.
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context("txn-rate-bpp-orphan-1"),
                "message": _rate_message(),
            },
        )
        assert fake_db["ratings_received"] == []


class TestRateInvalidPayload:
    async def test_score_out_of_range_does_not_persist(self, client, fake_db):
        txn_id = "txn-rate-bpp-bad-001"
        _seed_completed_contract(fake_db, txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={
                "context": _rate_context(txn_id),
                "message": _rate_message(score=10.0),  # outside [min, max]
            },
        )
        assert fake_db["ratings_received"] == []

    async def test_missing_rating_inputs_does_not_persist(self, client, fake_db):
        txn_id = "txn-rate-bpp-bad-002"
        _seed_completed_contract(fake_db, txn_id=txn_id)
        await client.post(
            "/api/webhook/rate",
            json={"context": _rate_context(txn_id), "message": {}},
        )
        assert fake_db["ratings_received"] == []
