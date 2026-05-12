"""
Contract tests for BPP transactional continuity (issue #14).

When a BPP receives init/confirm/status/cancel for a transactionId it never
ack'd via select, the handler MUST respond with a Beckn-compliant on_*
envelope carrying error.code = "30002" and MUST NOT mutate the contracts
table. This protects against cross-BPP misrouting from creating phantom rows.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.handlers import beckn_actions
from tests.factories.agents import make_beckn_context


UNKNOWN_TXN = "txn-never-seen-by-this-bpp"


@pytest.fixture
def mock_repo_empty():
    """Repo where every contract lookup returns None (txn unknown)."""
    with patch("app.handlers.beckn_actions.repo") as mock:
        mock.get_contract_by_txn = AsyncMock(return_value=None)
        mock.update_contract = AsyncMock(return_value=None)
        mock.create_contract = AsyncMock(return_value=None)
        yield mock


@pytest.mark.parametrize("action,handler", [
    ("init", beckn_actions.handle_init),
    ("confirm", beckn_actions.handle_confirm),
    ("status", beckn_actions.handle_status),
    ("cancel", beckn_actions.handle_cancel),
])
class TestUnknownTxnRejection:
    async def test_returns_error_30002(self, action, handler, mock_repo_empty):
        context = make_beckn_context(action, txn_id=UNKNOWN_TXN)
        response = await handler(context, {"contract": {}})

        assert "error" in response, f"on_{action} must carry top-level error"
        assert response["error"]["code"] == "30002"
        assert "ot found" in response["error"]["message"].lower() or \
               "not found" in response["error"]["message"].lower()

    async def test_response_action_is_on_prefixed(self, action, handler, mock_repo_empty):
        context = make_beckn_context(action, txn_id=UNKNOWN_TXN)
        response = await handler(context, {"contract": {}})

        assert response["context"]["action"] == f"on_{action}"
        assert response["context"]["transactionId"] == UNKNOWN_TXN

    async def test_does_not_create_phantom_contract(self, action, handler, mock_repo_empty):
        context = make_beckn_context(action, txn_id=UNKNOWN_TXN)
        await handler(context, {"contract": {}})

        mock_repo_empty.create_contract.assert_not_called()
        mock_repo_empty.update_contract.assert_not_called()

    async def test_no_message_field_when_rejecting(self, action, handler, mock_repo_empty):
        """An on_* error envelope should not echo phantom contract data."""
        context = make_beckn_context(action, txn_id=UNKNOWN_TXN)
        response = await handler(context, {"contract": {}})

        assert "message" not in response, (
            f"on_{action} error response must not include a synthetic message body"
        )


class TestConfirmDoesNotDispatchOnUnknownTxn:
    """Confirm has a side effect (orchestrator dispatch) that MUST be skipped."""

    async def test_orchestrator_not_called(self, mock_repo_empty):
        with patch("app.handlers.beckn_actions.orchestrator_client") as orch:
            orch.start_execution = AsyncMock()
            context = make_beckn_context("confirm", txn_id=UNKNOWN_TXN)

            await beckn_actions.handle_confirm(context, {"contract": {}})

            # Give any (incorrectly scheduled) background task a chance to run.
            import asyncio
            await asyncio.sleep(0.05)

            orch.start_execution.assert_not_called()
