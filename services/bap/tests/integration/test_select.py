"""
Integration tests for BAP POST /api/contracts/select.

Tests what the route does: builds a Beckn payload, sends it to ONIX,
and returns a transactionId. ONIX is mocked — we verify the outgoing
payload structure and the response, not ONIX's behavior.
"""

import json
import pytest


class TestSelectHappyPath:
    async def test_returns_200(self, client, mock_onix):
        response = await client.post("/api/contracts/select", json={
            "agent_id": "agent-summarizer-001",
            "offer_id": "offer-summarizer-basic",
        })
        assert response.status_code == 200

    async def test_returns_transaction_id(self, client, mock_onix):
        response = await client.post("/api/contracts/select", json={})
        assert "transactionId" in response.json()

    async def test_transaction_id_is_string(self, client, mock_onix):
        response = await client.post("/api/contracts/select", json={})
        assert isinstance(response.json()["transactionId"], str)

    async def test_returns_onix_ack(self, client, mock_onix):
        response = await client.post("/api/contracts/select", json={})
        data = response.json()
        assert data["onix_response"]["message"]["ack"]["status"] == "ACK"

    async def test_each_call_generates_unique_transaction_id(self, client, mock_onix):
        ids = set()
        for _ in range(5):
            r = await client.post("/api/contracts/select", json={})
            ids.add(r.json()["transactionId"])
        assert len(ids) == 5


class TestSelectPayloadSentToONIX:
    async def test_sends_post_to_onix_select_endpoint(self, client, mock_onix):
        await client.post("/api/contracts/select", json={})
        assert mock_onix["select"].called

    async def test_payload_context_action_is_select(self, client, mock_onix):
        await client.post("/api/contracts/select", json={})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        assert payload["context"]["action"] == "select"

    async def test_payload_context_has_bap_id(self, client, mock_onix):
        await client.post("/api/contracts/select", json={})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        assert payload["context"]["bapId"] == "bap.example.com"

    async def test_payload_context_has_transaction_id(self, client, mock_onix):
        await client.post("/api/contracts/select", json={})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        assert "transactionId" in payload["context"]

    async def test_payload_includes_requested_agent_id(self, client, mock_onix):
        await client.post("/api/contracts/select", json={"agent_id": "agent-code-reviewer-001"})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        resources = payload["message"]["contract"]["commitments"][0]["resources"]
        assert resources[0]["id"] == "agent-code-reviewer-001"

    async def test_payload_includes_requested_offer_id(self, client, mock_onix):
        await client.post("/api/contracts/select", json={"offer_id": "offer-code-review-basic"})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        offer = payload["message"]["contract"]["commitments"][0]["offer"]
        assert offer["id"] == "offer-code-review-basic"

    async def test_payload_quantity_defaults_to_1(self, client, mock_onix):
        await client.post("/api/contracts/select", json={})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        qty = payload["message"]["contract"]["commitments"][0]["resources"][0]["quantity"]
        assert qty["unitQuantity"] == 1

    async def test_custom_quantity_is_forwarded(self, client, mock_onix):
        await client.post("/api/contracts/select", json={"quantity": 3})
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        qty = payload["message"]["contract"]["commitments"][0]["resources"][0]["quantity"]
        assert qty["unitQuantity"] == 3

    async def test_provided_transaction_id_is_reused(self, client, mock_onix):
        given_txn = "my-fixed-txn-id-001"
        response = await client.post("/api/contracts/select", json={"transaction_id": given_txn})
        assert response.json()["transactionId"] == given_txn
        payload = json.loads(mock_onix["select"].calls.last.request.content)
        assert payload["context"]["transactionId"] == given_txn


class TestSelectErrorScenarios:
    async def test_empty_payload_uses_defaults(self, client, mock_onix):
        response = await client.post("/api/contracts/select", json={})
        assert response.status_code == 200

    async def test_onix_unavailable_returns_error(self, client):
        import httpx
        import respx
        with respx.mock() as mock:
            mock.post("http://onix-bap:8081/bap/caller/select").mock(
                side_effect=httpx.ConnectError("ONIX unreachable")
            )
            response = await client.post("/api/contracts/select", json={})
            assert response.status_code in (500, 503, 502, 504)
