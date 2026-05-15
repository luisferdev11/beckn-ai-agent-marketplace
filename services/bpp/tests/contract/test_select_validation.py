"""
Contract tests for BPP select-time agent validation (issue #15).

When a BAP sends `select` with a resource id that does not match any agent in
the BPP catalog, the handler MUST respond with a Beckn-compliant on_select
envelope carrying error.code = "30001" and MUST NOT create a DRAFT row in the
contracts table. This prevents the symptom where a fake agent_id was returning
on_select with price=0.00 (only the 18% GST on nothing) and leaving a phantom
DRAFT contract behind.
"""

import pytest

from app.handlers import beckn_actions
from tests.factories.agents import make_beckn_context, make_select_contract_message


UNKNOWN_AGENT_ID = "agent-no-existe-666"
KNOWN_AGENT_ID = "agent-summarizer-001"
UNKNOWN_AGENT_TXN = "txn-bpp-unknown-agent-001"


class TestSelectRejectsUnknownAgent:
    async def test_returns_error_30001(self, fake_db):
        context = make_beckn_context("select", txn_id=UNKNOWN_AGENT_TXN)
        message = make_select_contract_message(
            agent_id=UNKNOWN_AGENT_ID, txn_id=UNKNOWN_AGENT_TXN
        )

        response = await beckn_actions.handle_select(context, message)

        assert "error" in response, "on_select must carry top-level error"
        assert response["error"]["code"] == "30001"

    async def test_error_message_identifies_agent(self, fake_db):
        """Operators need to see which agent_id failed so catalog drift is debuggable."""
        context = make_beckn_context("select", txn_id=UNKNOWN_AGENT_TXN)
        message = make_select_contract_message(
            agent_id=UNKNOWN_AGENT_ID, txn_id=UNKNOWN_AGENT_TXN
        )

        response = await beckn_actions.handle_select(context, message)

        assert UNKNOWN_AGENT_ID in response["error"]["message"]

    async def test_response_action_is_on_select(self, fake_db):
        context = make_beckn_context("select", txn_id=UNKNOWN_AGENT_TXN)
        message = make_select_contract_message(
            agent_id=UNKNOWN_AGENT_ID, txn_id=UNKNOWN_AGENT_TXN
        )

        response = await beckn_actions.handle_select(context, message)

        assert response["context"]["action"] == "on_select"
        assert response["context"]["transactionId"] == UNKNOWN_AGENT_TXN

    async def test_does_not_create_draft_contract(self, fake_db):
        """The invariant `row exists ⇔ legitimate select happened` must hold."""
        context = make_beckn_context("select", txn_id=UNKNOWN_AGENT_TXN)
        message = make_select_contract_message(
            agent_id=UNKNOWN_AGENT_ID, txn_id=UNKNOWN_AGENT_TXN
        )

        await beckn_actions.handle_select(context, message)

        assert UNKNOWN_AGENT_TXN not in fake_db["contracts"]

    async def test_no_message_field_when_rejecting(self, fake_db):
        """An on_select error envelope should not echo phantom contract data."""
        context = make_beckn_context("select", txn_id=UNKNOWN_AGENT_TXN)
        message = make_select_contract_message(
            agent_id=UNKNOWN_AGENT_ID, txn_id=UNKNOWN_AGENT_TXN
        )

        response = await beckn_actions.handle_select(context, message)

        assert "message" not in response, (
            "on_select error response must not include a synthetic message body"
        )


class TestSelectRejectsWhenAnyResourceUnknown:
    """All-or-nothing: a single unknown resource fails the whole select."""

    async def test_mixed_resources_one_unknown_rejects(self, fake_db):
        txn_id = "txn-mixed-resources-001"
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )
        # Inject a second resource that does not exist into the same commitment.
        message["contract"]["commitments"][0]["resources"].append({
            "id": UNKNOWN_AGENT_ID,
            "descriptor": {"name": "Fake agent", "code": UNKNOWN_AGENT_ID},
            "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
        })
        context = make_beckn_context("select", txn_id=txn_id)

        response = await beckn_actions.handle_select(context, message)

        assert response.get("error", {}).get("code") == "30001"
        assert txn_id not in fake_db["contracts"]


class TestSelectRejectsUnavailableAgent:
    """Agents whose status != 'active' are treated like unknown agents.

    The CHECK constraint on agents.status (001_schema.sql) admits
    'active' | 'inactive' | 'deprecated'. The select handler must reject the
    latter two with the same error code as a missing agent — from the user's
    perspective, "agent does not exist" and "agent exists but is unavailable"
    are indistinguishable: in both cases the selected resource cannot be
    fulfilled. See issue #15.
    """

    @pytest.mark.parametrize("inactive_status", ["inactive", "deprecated"])
    async def test_unavailable_agent_returns_30001(self, fake_db, inactive_status):
        fake_db["agents"][KNOWN_AGENT_ID]["status"] = inactive_status
        txn_id = f"txn-bpp-{inactive_status}-001"
        context = make_beckn_context("select", txn_id=txn_id)
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )

        response = await beckn_actions.handle_select(context, message)

        assert response.get("error", {}).get("code") == "30001"
        assert KNOWN_AGENT_ID in response["error"]["message"]

    @pytest.mark.parametrize("inactive_status", ["inactive", "deprecated"])
    async def test_unavailable_agent_does_not_create_contract(self, fake_db, inactive_status):
        fake_db["agents"][KNOWN_AGENT_ID]["status"] = inactive_status
        txn_id = f"txn-bpp-{inactive_status}-002"
        context = make_beckn_context("select", txn_id=txn_id)
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )

        await beckn_actions.handle_select(context, message)

        assert txn_id not in fake_db["contracts"]

    async def test_unavailable_agent_response_has_no_message(self, fake_db):
        fake_db["agents"][KNOWN_AGENT_ID]["status"] = "inactive"
        txn_id = "txn-bpp-inactive-003"
        context = make_beckn_context("select", txn_id=txn_id)
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )

        response = await beckn_actions.handle_select(context, message)

        assert "message" not in response


class TestSelectAcceptsKnownAgent:
    """Regression guard: a valid select must still succeed and price normally."""

    async def test_known_agent_returns_normal_consideration(self, fake_db):
        txn_id = "txn-bpp-known-agent-001"
        context = make_beckn_context("select", txn_id=txn_id)
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )

        response = await beckn_actions.handle_select(context, message)

        assert "error" not in response
        assert "message" in response
        consideration = response["message"]["contract"]["consideration"]
        assert len(consideration) > 0
        # Summarizer is seeded at 6.00 INR + 18% GST = 7.08
        assert consideration[0]["price"]["value"] == "7.08"

    async def test_known_agent_creates_draft_contract(self, fake_db):
        txn_id = "txn-bpp-known-agent-002"
        context = make_beckn_context("select", txn_id=txn_id)
        message = make_select_contract_message(
            agent_id=KNOWN_AGENT_ID, txn_id=txn_id
        )

        await beckn_actions.handle_select(context, message)

        assert txn_id in fake_db["contracts"]
        assert fake_db["contracts"][txn_id]["status"] == "DRAFT"
