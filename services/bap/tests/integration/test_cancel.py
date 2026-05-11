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


def _cb(cb_dict):
    return cb_dict["context"], cb_dict["message"]
