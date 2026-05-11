"""
Integration tests for BAP POST /api/contracts/init.

Init requires a prior select (issue #12 — no phantom contracts). Each test
either seeds a transaction via /select first, or asserts that calling
init on an unknown transaction returns 404.
"""

import json
import pytest
from tests.factories.beckn import make_on_select_callback
from app import store as bap_store


class TestInitHappyPath:
    async def test_returns_200_when_transaction_exists(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-init-001")
        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.status_code == 200

    async def test_returns_transaction_id(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-init-002")
        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.json()["transactionId"] == txn_id

    async def test_returns_ack(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-init-003")
        response = await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert response.json()["onix_response"]["message"]["ack"]["status"] == "ACK"

    async def test_sends_to_onix_init_endpoint(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-init-004")
        await client.post("/api/contracts/init", json={"transaction_id": txn_id})
        assert mock_onix["init"].called

    async def test_init_payload_uses_stored_commitments(self, client, mock_onix, seeded_txn):
        txn_id = await seeded_txn("txn-init-005", agent_id="agent-code-reviewer-001")
        # Simulate an on_select callback that enriches the contract with the
        # negotiated commitments — same as in real flow.
        cb = make_on_select_callback(txn_id, agent_id="agent-code-reviewer-001")
        await bap_store.store_callback(cb["context"], cb["message"])

        await client.post("/api/contracts/init", json={"transaction_id": txn_id})

        payload = json.loads(mock_onix["init"].calls.last.request.content)
        resources = payload["message"]["contract"]["commitments"][0]["resources"]
        assert resources[0]["id"] == "agent-code-reviewer-001"


class TestInitRejectsUnknownTransaction:
    async def test_unknown_txn_returns_404(self, client, mock_onix):
        """A transaction that never went through /select must be rejected.
        Otherwise the resulting on_init callback would (used to) materialize a
        phantom contract row. See issue #12.
        """
        response = await client.post("/api/contracts/init", json={"transaction_id": "txn-never-selected"})
        assert response.status_code == 404

    async def test_unknown_txn_does_not_call_onix(self, client, mock_onix):
        await client.post("/api/contracts/init", json={"transaction_id": "txn-never-selected"})
        assert not mock_onix["init"].called

    async def test_unknown_txn_error_payload_is_structured(self, client, mock_onix):
        response = await client.post("/api/contracts/init", json={"transaction_id": "txn-never-selected"})
        body = response.json()
        assert body["detail"]["error"] == "transaction_not_found"
        assert body["detail"]["transaction_id"] == "txn-never-selected"
