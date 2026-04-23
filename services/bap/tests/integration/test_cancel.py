"""
Integration tests for BAP POST /api/contracts/cancel.

The BPP already has handle_cancel(). This test suite drives the BAP side.
"""

import json
import pytest
from tests.factories.beckn import make_on_select_callback, make_on_confirm_callback
from app import store as bap_store


class TestCancelHappyPath:
    async def test_cancel_returns_200(self, client, mock_onix):
        response = await client.post("/api/contracts/cancel", json={"transaction_id": "txn-cancel-001"})
        assert response.status_code == 200

    async def test_cancel_returns_transaction_id(self, client, mock_onix):
        response = await client.post("/api/contracts/cancel", json={"transaction_id": "txn-cancel-002"})
        assert response.json()["transactionId"] == "txn-cancel-002"

    async def test_cancel_sends_to_onix(self, client, mock_onix):
        await client.post("/api/contracts/cancel", json={"transaction_id": "txn-cancel-003"})
        assert mock_onix["cancel"].called

    async def test_cancel_payload_action_is_cancel(self, client, mock_onix):
        await client.post("/api/contracts/cancel", json={"transaction_id": "txn-cancel-004"})
        payload = json.loads(mock_onix["cancel"].calls.last.request.content)
        assert payload["context"]["action"] == "cancel"

    async def test_cancel_uses_stored_contract_data(self, client, mock_onix):
        txn_id = "txn-cancel-005"
        bap_store.store_callback(make_on_select_callback(txn_id)["context"],
                                 make_on_select_callback(txn_id)["message"])
        bap_store.store_callback(make_on_confirm_callback(txn_id)["context"],
                                 make_on_confirm_callback(txn_id)["message"])
        response = await client.post("/api/contracts/cancel", json={"transaction_id": txn_id})
        assert response.status_code == 200


class TestCancelErrorScenarios:
    async def test_cancel_without_transaction_id_returns_422(self, client, mock_onix):
        response = await client.post("/api/contracts/cancel", json={})
        assert response.status_code == 422
