"""Integration tests for BAP POST /api/contracts/rate.

`rate` is the last Beckn v2 verb in the buyer's post-fulfillment loop:
the user submits a numeric score (1..5) plus optional free-form feedback
for one of the entities involved in a completed contract (typically the
agent that fulfilled the task).

Behavioural contract:

  - The route requires ``transaction_id`` and ``score`` in the body;
    422 on missing.
  - ``score`` is bounded to [1.0, 5.0]; out-of-range → 422.
  - The transaction must already exist (same gate as cancel/init/etc.);
    unknown txn → 404.
  - On success the endpoint:
      1. records the rating in the BAP ``ratings_sent`` log,
      2. POSTs a Beckn v2 ``/rate`` envelope to ONIX with the
         RateAction message shape (``ratingInputs`` array with one
         entry per target),
      3. returns 200 with ``{transactionId, onix_response}``.
  - Re-rating the same target on the same transaction overwrites the
    previous score (upsert), it does not duplicate.
"""
from __future__ import annotations

import json
import pytest


class TestRateHappyPath:
    async def test_rate_returns_200(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-001")
        resp = await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.5},
        )
        assert resp.status_code == 200

    async def test_rate_returns_transaction_id(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-002")
        resp = await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 5.0},
        )
        assert resp.json()["transactionId"] == txn_id

    async def test_rate_sends_to_onix(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-003")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.0},
        )
        assert mock_onix["rate"].called

    async def test_rate_payload_action_is_rate(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-004")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 3.5},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        assert payload["context"]["action"] == "rate"


class TestRatePayloadIsV2Compliant:
    """Beckn v2 RateAction message:

        {"ratingInputs": [{"target": {...}, "range": {...},
                           "feedbackFormSubmission": {...} (optional)}]}
    """

    async def test_payload_carries_ratinginputs_array(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-v2-001")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.0},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        assert isinstance(payload["message"]["ratingInputs"], list)
        assert len(payload["message"]["ratingInputs"]) >= 1

    async def test_rating_input_target_carries_agent_id(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-v2-002")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.0,
                  "target_id": "agent-summarizer-001"},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        rinput = payload["message"]["ratingInputs"][0]
        assert rinput["target"]["id"] == "agent-summarizer-001"

    async def test_rating_input_range_carries_score(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-v2-003")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.5},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        rinput = payload["message"]["ratingInputs"][0]
        # We expose score as range.{min, max, value} so the BPP knows the
        # scale we rated against.
        assert rinput["range"]["value"] == 4.5
        assert rinput["range"]["min"] == 1.0
        assert rinput["range"]["max"] == 5.0

    async def test_feedback_text_becomes_feedback_form_submission(
        self, client, mock_onix, seeded_txn
    ):
        txn_id = await seeded_txn("txn-rate-v2-004")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.0,
                  "feedback": "Great review, very thorough."},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        rinput = payload["message"]["ratingInputs"][0]
        assert "feedbackFormSubmission" in rinput

    async def test_feedback_omitted_when_not_provided(
        self, client, mock_onix, seeded_txn
    ):
        # Empty feedback must NOT emit a junk feedbackFormSubmission block.
        # Beckn v2 marks the field optional; spurious empty objects bloat
        # the audit log.
        txn_id = await seeded_txn("txn-rate-v2-005")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.0},
        )
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        rinput = payload["message"]["ratingInputs"][0]
        assert "feedbackFormSubmission" not in rinput


class TestRateValidationErrors:
    async def test_missing_transaction_id_returns_422(self, client, mock_onix):
        resp = await client.post("/api/contracts/rate", json={"score": 4.0})
        assert resp.status_code == 422

    async def test_missing_score_returns_422(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-err-001")
        resp = await client.post(
            "/api/contracts/rate", json={"transaction_id": txn_id}
        )
        assert resp.status_code == 422

    async def test_score_below_minimum_returns_422(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-err-002")
        resp = await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 0.5},
        )
        assert resp.status_code == 422

    async def test_score_above_maximum_returns_422(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-rate-err-003")
        resp = await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 5.5},
        )
        assert resp.status_code == 422


class TestRateRejectsUnknownTransaction:
    async def test_unknown_txn_returns_404(self, client, mock_onix):
        resp = await client.post(
            "/api/contracts/rate",
            json={"transaction_id": "txn-never-seleted", "score": 4.0},
        )
        assert resp.status_code == 404

    async def test_unknown_txn_does_not_call_onix(self, client, mock_onix):
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": "txn-never-seleted", "score": 4.0},
        )
        assert not mock_onix["rate"].called


class TestRateIsPersisted:
    async def test_rating_is_recorded_in_local_log(
        self, client, mock_onix, seeded_txn, fake_db
    ):
        txn_id = await seeded_txn("txn-rate-persist-001")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 4.5,
                  "feedback": "Solid output."},
        )
        # Each test seeds one row in the in-memory ratings log.
        ratings = fake_db["ratings_sent"]
        match = [r for r in ratings if r["transaction_id"] == txn_id]
        assert len(match) == 1
        assert float(match[0]["score"]) == 4.5
        assert match[0]["feedback"] == "Solid output."

    async def test_re_rating_overwrites_score(
        self, client, mock_onix, seeded_txn, fake_db
    ):
        txn_id = await seeded_txn("txn-rate-persist-002")
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 3.0},
        )
        await client.post(
            "/api/contracts/rate",
            json={"transaction_id": txn_id, "score": 5.0},
        )
        ratings = fake_db["ratings_sent"]
        match = [r for r in ratings if r["transaction_id"] == txn_id]
        # Upsert semantics: one row, latest score wins.
        assert len(match) == 1
        assert float(match[0]["score"]) == 5.0
