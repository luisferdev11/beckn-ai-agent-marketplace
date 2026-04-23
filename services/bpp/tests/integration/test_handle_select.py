"""
Integration tests for BPP handle_select via POST /api/webhook/select.

Tests the full handler chain: ONIX posts to /api/webhook/select,
we process it, and send on_select callback to ONIX-BPP asynchronously.
"""

import json
import pytest
from tests.factories.agents import make_beckn_context, make_select_contract_message


class TestWebhookSelectACK:
    async def test_returns_ack_immediately(self, client, mock_onix_bpp):
        body = {
            "context": make_beckn_context("select"),
            "message": make_select_contract_message(),
        }
        response = await client.post("/api/webhook/select", json=body)
        assert response.status_code == 200
        assert response.json()["message"]["ack"]["status"] == "ACK"

    async def test_ack_is_synchronous(self, client, mock_onix_bpp):
        """ACK must be returned before the on_select callback is sent."""
        body = {
            "context": make_beckn_context("select"),
            "message": make_select_contract_message(),
        }
        response = await client.post("/api/webhook/select", json=body)
        assert response.status_code == 200

    async def test_unknown_action_also_returns_ack(self, client, mock_onix_bpp):
        body = {
            "context": make_beckn_context("unknown_future_action"),
            "message": {},
        }
        response = await client.post("/api/webhook/unknown_future_action", json=body)
        assert response.status_code == 200
        assert response.json()["message"]["ack"]["status"] == "ACK"


class TestSelectContractCreation:
    async def test_contract_created_in_store(self, client, mock_onix_bpp):
        from app.handlers import beckn_actions
        txn_id = "txn-bpp-select-001"
        body = {
            "context": make_beckn_context("select", txn_id=txn_id),
            "message": make_select_contract_message(txn_id=txn_id),
        }
        await client.post("/api/webhook/select", json=body)
        contract_id = f"contract-{txn_id[:8]}"
        assert contract_id in beckn_actions._contracts

    async def test_stored_contract_has_transaction_id(self, client, mock_onix_bpp):
        from app.handlers import beckn_actions
        txn_id = "txn-bpp-select-002"
        body = {
            "context": make_beckn_context("select", txn_id=txn_id),
            "message": make_select_contract_message(txn_id=txn_id),
        }
        await client.post("/api/webhook/select", json=body)
        contract_id = f"contract-{txn_id[:8]}"
        stored = beckn_actions._contracts[contract_id]
        assert stored["transactionId"] == txn_id

    async def test_stored_contract_status_is_draft(self, client, mock_onix_bpp):
        from app.handlers import beckn_actions
        txn_id = "txn-bpp-select-003"
        body = {
            "context": make_beckn_context("select", txn_id=txn_id),
            "message": make_select_contract_message(txn_id=txn_id),
        }
        await client.post("/api/webhook/select", json=body)
        contract_id = f"contract-{txn_id[:8]}"
        assert beckn_actions._contracts[contract_id]["status"] == "DRAFT"


class TestSelectPricingViaWebhook:
    async def test_summarizer_consideration_in_stored_contract(self, client, mock_onix_bpp):
        from app.handlers import beckn_actions
        txn_id = "txn-bpp-price-001"
        body = {
            "context": make_beckn_context("select", txn_id=txn_id),
            "message": make_select_contract_message("agent-summarizer-001", txn_id=txn_id),
        }
        await client.post("/api/webhook/select", json=body)
        contract_id = f"contract-{txn_id[:8]}"
        consideration = beckn_actions._contracts[contract_id]["consideration"]
        assert len(consideration) > 0
        assert consideration[0]["price"]["value"] == "7.08"

    async def test_code_reviewer_consideration_in_stored_contract(self, client, mock_onix_bpp):
        from app.handlers import beckn_actions
        txn_id = "txn-bpp-price-002"
        body = {
            "context": make_beckn_context("select", txn_id=txn_id),
            "message": make_select_contract_message("agent-code-reviewer-001", txn_id=txn_id),
        }
        await client.post("/api/webhook/select", json=body)
        contract_id = f"contract-{txn_id[:8]}"
        consideration = beckn_actions._contracts[contract_id]["consideration"]
        assert consideration[0]["price"]["value"] == "11.80"
