"""
Integration tests for BAP POST /api/contracts/init.
"""

import json
import pytest
from tests.factories.beckn import make_on_select_callback
from app import store as bap_store


class TestInitHappyPath:
    async def test_returns_200_when_transaction_exists(self, client, mock_onix):
        # Simulate an on_select that pre-populated the store
        txn_id = "txn-init-001"
        cb = make_on_select_callback(txn_id)
        bap_store.store_callback(cb["context"], cb["message"])

        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.status_code == 200

    async def test_returns_transaction_id(self, client, mock_onix):
        txn_id = "txn-init-002"
        cb = make_on_select_callback(txn_id)
        bap_store.store_callback(cb["context"], cb["message"])

        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.json()["transactionId"] == txn_id

    async def test_returns_ack(self, client, mock_onix):
        txn_id = "txn-init-003"
        cb = make_on_select_callback(txn_id)
        bap_store.store_callback(cb["context"], cb["message"])

        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.json()["onix_response"]["message"]["ack"]["status"] == "ACK"

    async def test_sends_to_onix_init_endpoint(self, client, mock_onix):
        txn_id = "txn-init-004"
        bap_store.store_callback(make_on_select_callback(txn_id)["context"],
                                 make_on_select_callback(txn_id)["message"])
        await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert mock_onix["init"].called

    async def test_init_payload_uses_stored_commitments(self, client, mock_onix):
        txn_id = "txn-init-005"
        cb = make_on_select_callback(txn_id, agent_id="agent-code-reviewer-001")
        bap_store.store_callback(cb["context"], cb["message"])

        await client.post("/api/contracts/init", json={"transaction_id": txn_id})

        payload = json.loads(mock_onix["init"].calls.last.request.content)
        resources = payload["message"]["contract"]["commitments"][0]["resources"]
        assert resources[0]["id"] == "agent-code-reviewer-001"

    async def test_init_works_with_no_prior_on_select(self, client, mock_onix):
        """Init should fallback gracefully when on_select hasn't arrived yet."""
        response = await client.post("/api/contracts/init", json={"transaction_id": "txn-no-prior"})
        assert response.status_code == 200
