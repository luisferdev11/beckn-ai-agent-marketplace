"""
Integration tests for BAP POST /api/contracts/cancel.

Like init/confirm/status, cancel requires a prior select (issue #12).
"""

import json
import pytest
from tests.factories.beckn import make_on_select_callback, make_on_confirm_callback
from app import store as bap_store


class TestCancelHappyPath:
    async def test_cancel_returns_200(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-001")
        response = await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        assert response.status_code == 200

    async def test_cancel_returns_transaction_id(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-002")
        response = await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        assert response.json()["transactionId"] == txn_id

    async def test_cancel_sends_to_onix(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-003")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        assert mock_onix["cancel"].called

    async def test_cancel_payload_action_is_cancel(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-004")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        assert payload["context"]["action"] == "cancel"

    async def test_cancel_uses_stored_contract_data(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-005")
        await bap_store.store_callback(*_cb(make_on_select_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        response = await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        assert response.status_code == 200


class TestCancelRejectsUnknownTransaction:
    async def test_unknown_txn_returns_404(self, client, mock_onix):
        response = await client.post("/api/contracts/cancel", json={"transaction_id": "txn-no-select"})
        assert response.status_code == 404

    async def test_unknown_txn_does_not_call_onix(self, client, mock_onix):
        await client.post("/api/contracts/cancel", json={"transaction_id": "txn-no-select"})
        assert not mock_onix["cancel"].called


class TestCancelErrorScenarios:
    async def test_cancel_without_transaction_id_returns_422(self, client, mock_onix):
        response = await client.post("/api/contracts/cancel", json={})
        assert response.status_code == 422


class TestCancelPayloadIsV2Compliant:
    """Beckn v2 schema for the cancel payload:

      - Commitment.status.code enum: {DRAFT, ACTIVE, CLOSED}
      - Contract.status.code enum:   {DRAFT, ACTIVE, CANCELLED, COMPLETE}
      - Contract has additionalProperties:false (no free-form ``reason``).

    The previous implementation set commitments to ``CANCELLED`` and added
    a top-level ``reason`` block — both rejected by ONIX schema validation.
    """

    async def test_commitment_status_code_is_closed(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-closed-001")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        for commitment in payload["message"]["contract"]["commitments"]:
            assert commitment["status"]["descriptor"]["code"] == "CLOSED"

    async def test_commitment_status_code_is_never_cancelled(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-closed-002")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        codes = {
            c["status"]["descriptor"]["code"]
            for c in payload["message"]["contract"]["commitments"]
        }
        assert "CANCELLED" not in codes

    async def test_contract_status_code_is_cancelled(self, client, mock_onix, seeded_txn):
        # Contract.status is a Descriptor directly (NOT {descriptor: {...}})
        # per the spec — different from Commitment.status which is nested.
        txn_id = await seeded_txn("txn-cancel-closed-003")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        status = payload["message"]["contract"]["status"]
        assert status.get("code") == "CANCELLED"
        assert "descriptor" not in status  # the v1-style wrapper is the bug we fixed

    async def test_contract_has_no_unsupported_reason_field(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-cancel-closed-004")
        await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        assert "reason" not in payload["message"]["contract"]


def _cb(cb_dict):
    return cb_dict["context"], cb_dict["message"]
