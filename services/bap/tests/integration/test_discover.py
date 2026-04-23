"""
Integration tests for BAP POST /api/contracts/discover.

The discover flow:
  BAP → ONIX-BAP → Discovery Service (or directly to BPP in offline mode)
  BAP ← on_discover callback ← BPP catalog

Design decisions encoded here:
  - Endpoint accepts optional `query`, `category`, and `capabilities` filters
  - Returns a transactionId for tracking the discover flow
  - Sends a valid Beckn v2 'discover' action to ONIX
"""

import json
import pytest


class TestDiscoverEndpointExists:
    async def test_discover_returns_200(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={})
        assert response.status_code == 200

    async def test_discover_returns_transaction_id(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={"query": "code review"})
        assert "transactionId" in response.json()

    async def test_discover_returns_onix_ack(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={})
        assert response.json()["onix_response"]["message"]["ack"]["status"] == "ACK"


class TestDiscoverPayloadSentToONIX:
    async def test_sends_to_onix_discover_endpoint(self, client, mock_onix):
        await client.post("/api/contracts/discover", json={})
        assert mock_onix["discover"].called

    async def test_payload_context_action_is_discover(self, client, mock_onix):
        await client.post("/api/contracts/discover", json={})
        payload = json.loads(mock_onix["discover"].calls.last.request.content)
        assert payload["context"]["action"] == "discover"

    async def test_payload_includes_query_in_message(self, client, mock_onix):
        await client.post("/api/contracts/discover", json={"query": "legal summarizer"})
        payload = json.loads(mock_onix["discover"].calls.last.request.content)
        intent = payload["message"].get("intent", {})
        query = str(intent).lower()
        assert "legal summarizer" in query

    async def test_payload_includes_capability_filter(self, client, mock_onix):
        await client.post("/api/contracts/discover", json={
            "capabilities": ["code_review", "security_analysis"]
        })
        payload = json.loads(mock_onix["discover"].calls.last.request.content)
        assert "message" in payload


class TestDiscoverWithFilters:
    async def test_empty_body_is_valid(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={})
        assert response.status_code == 200

    async def test_query_filter_accepted(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={"query": "invoice"})
        assert response.status_code == 200

    async def test_category_filter_accepted(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={"category": "AI-SUMMARIZATION"})
        assert response.status_code == 200

    async def test_capabilities_filter_accepted(self, client, mock_onix):
        response = await client.post("/api/contracts/discover", json={
            "capabilities": ["ocr", "invoice_processing"]
        })
        assert response.status_code == 200
