"""
Integration tests for BPP handle_confirm via POST /api/webhook/confirm.

Confirm activates the contract and dispatches agent execution to the orchestrator.
"""

import pytest
from tests.factories.agents import make_beckn_context, make_select_contract_message


def _seed_contract(fake_db: dict, txn_id: str, agent_id: str = "agent-code-reviewer-001") -> str:
    """Pre-populate the contract store as if select already happened.

    Writes directly to fake_db['contracts'] using the Postgres-shaped row
    (keyed by transaction_id, snake_case fields).
    """
    contract_code = f"contract-{txn_id[:8]}"
    fake_db["contracts"][txn_id] = {
        "contract_code": contract_code,
        "transaction_id": txn_id,
        "status": "DRAFT",
        "agent_id": None,
        "provider_id": 1,
        "bap_id": "bap.example.com",
        "bpp_id": "bpp.example.com",
        "participants": [{"id": "participant-buyer-001", "descriptor": {"name": "Test User", "code": "buyer"}}],
        "commitments": [{
            "id": "commitment-001",
            "resources": [{"id": agent_id, "descriptor": {"name": "AI Agent"}, "quantity": {"unitQuantity": 1, "unitCode": "UNIT"}}],
            "offer": {"id": "offer-code-review-basic"},
        }],
        "consideration": [{"price": {"currency": "INR", "value": "11.80"}}],
        "performance": [{"id": "perf-001"}],
        "settlements": [{"id": "settlement-001", "status": "DRAFT"}],
        "total_amount": None,
        "currency": "INR",
        "execution_id": None,
    }
    return contract_code


class TestConfirmACK:
    async def test_returns_ack(self, client, mock_onix_bpp, mock_orchestrator, fake_db):
        txn_id = "txn-confirm-001"
        contract_code = _seed_contract(fake_db, txn_id)
        body = {
            "context": make_beckn_context("confirm", txn_id=txn_id),
            "message": {"contract": {"id": contract_code}},
        }
        response = await client.post("/api/webhook/confirm", json=body)
        assert response.status_code == 200
        assert response.json()["message"]["ack"]["status"] == "ACK"


class TestConfirmActivatesContract:
    async def test_contract_status_becomes_active(self, client, mock_onix_bpp, mock_orchestrator, fake_db):
        txn_id = "txn-confirm-002"
        contract_code = _seed_contract(fake_db, txn_id)
        body = {
            "context": make_beckn_context("confirm", txn_id=txn_id),
            "message": {"contract": {"id": contract_code}},
        }
        await client.post("/api/webhook/confirm", json=body)
        # Give asyncio time to run _dispatch_to_orchestrator
        import asyncio
        await asyncio.sleep(0.05)
        assert fake_db["contracts"][txn_id]["status"] == "ACTIVE"

    async def test_orchestrator_is_called_after_confirm(self, client, mock_onix_bpp, mock_orchestrator, fake_db):
        txn_id = "txn-confirm-003"
        contract_code = _seed_contract(fake_db, txn_id, "agent-code-reviewer-001")
        body = {
            "context": make_beckn_context("confirm", txn_id=txn_id),
            "message": {"contract": {"id": contract_code}},
        }
        await client.post("/api/webhook/confirm", json=body)

        import asyncio
        await asyncio.sleep(0.05)

        mock_start, _ = mock_orchestrator
        mock_start.assert_called_once()
        call_args = mock_start.call_args[0][0]
        assert call_args["agent_id"] == "agent-code-reviewer-001"

    async def test_execution_id_stored_in_contract(self, client, mock_onix_bpp, mock_orchestrator, fake_db):
        txn_id = "txn-confirm-004"
        contract_code = _seed_contract(fake_db, txn_id)
        body = {
            "context": make_beckn_context("confirm", txn_id=txn_id),
            "message": {"contract": {"id": contract_code}},
        }
        await client.post("/api/webhook/confirm", json=body)

        import asyncio
        await asyncio.sleep(0.05)

        assert fake_db["contracts"][txn_id].get("execution_id") == "exec-test-001"


class TestConfirmWithNoStoredContract:
    async def test_returns_ack_even_without_prior_select(self, client, mock_onix_bpp, mock_orchestrator):
        """Confirm should not crash if there is no stored contract."""
        body = {
            "context": make_beckn_context("confirm", txn_id="txn-orphan-001"),
            "message": {"contract": {}},
        }
        response = await client.post("/api/webhook/confirm", json=body)
        assert response.status_code == 200
