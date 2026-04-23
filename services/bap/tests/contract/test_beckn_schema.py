"""
Beckn protocol contract tests for the BAP.

These tests verify that the messages we produce and receive conform to
Beckn v2 spec. They are the regression net for protocol changes and
catch bugs that unit tests miss (e.g. missing @context in performanceAttributes).

Tests here are NOT about business logic — they are about protocol compliance.
"""

import pytest
from tests.factories.beckn import (
    make_context,
    make_on_select_callback,
    make_on_confirm_callback,
    make_on_status_completed_callback,
)
from app import store as bap_store


class TestContextFields:
    """Every Beckn context must have these fields regardless of action."""

    @pytest.mark.parametrize("action", ["on_select", "on_init", "on_confirm", "on_status"])
    def test_context_has_required_fields(self, action):
        ctx = make_context(action)
        required = ("networkId", "action", "version", "bapId", "bapUri",
                     "transactionId", "messageId", "timestamp", "ttl")
        for field in required:
            assert field in ctx, f"[{action}] Missing required context field: {field}"

    @pytest.mark.parametrize("action", ["on_select", "on_init", "on_confirm", "on_status"])
    def test_on_action_prefix_is_correct(self, action):
        ctx = make_context(action)
        assert ctx["action"].startswith("on_"), f"Response context must have on_* action, got: {ctx['action']}"

    def test_ttl_is_iso8601_duration(self):
        ctx = make_context("on_select")
        ttl = ctx["ttl"]
        assert ttl.startswith("P"), f"TTL must be ISO 8601 duration, got: {ttl}"

    def test_version_is_2(self):
        ctx = make_context("on_select")
        assert ctx["version"] == "2.0.0"


class TestOnSelectSchema:
    def test_on_select_has_contract(self):
        cb = make_on_select_callback("txn-001")
        assert "contract" in cb["message"]

    def test_on_select_contract_has_consideration(self):
        cb = make_on_select_callback("txn-001")
        contract = cb["message"]["contract"]
        assert "consideration" in contract
        assert len(contract["consideration"]) > 0

    def test_on_select_consideration_has_price_with_currency(self):
        cb = make_on_select_callback("txn-001")
        for c in cb["message"]["contract"]["consideration"]:
            assert "price" in c
            assert "currency" in c["price"]
            assert "value" in c["price"]

    def test_on_select_consideration_has_breakup(self):
        cb = make_on_select_callback("txn-001")
        for c in cb["message"]["contract"]["consideration"]:
            assert "breakup" in c
            assert len(c["breakup"]) > 0

    def test_on_select_has_commitments(self):
        cb = make_on_select_callback("txn-001")
        assert len(cb["message"]["contract"]["commitments"]) > 0

    def test_on_select_has_participants(self):
        cb = make_on_select_callback("txn-001")
        assert len(cb["message"]["contract"]["participants"]) > 0


class TestOnStatusSchema:
    def test_on_status_has_performance(self):
        cb = make_on_status_completed_callback("txn-001")
        contract = cb["message"]["contract"]
        assert "performance" in contract
        assert len(contract["performance"]) > 0

    def test_on_status_performance_has_attributes(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            assert "performanceAttributes" in perf

    def test_on_status_performance_attributes_has_json_ld_context(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            attrs = perf["performanceAttributes"]
            assert "@context" in attrs, "performanceAttributes must have @context (JSON-LD)"
            assert "@type" in attrs, "performanceAttributes must have @type (JSON-LD)"

    def test_on_status_performance_attributes_type_is_agent_execution(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            assert perf["performanceAttributes"]["@type"] == "beckn:AgentExecution"

    def test_on_status_completed_has_tokens_used(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            attrs = perf["performanceAttributes"]
            assert "tokensUsed" in attrs
            tokens = attrs["tokensUsed"]
            assert "input" in tokens
            assert "output" in tokens
            assert "total" in tokens

    def test_on_status_completed_has_latency(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            assert "latencyMs" in perf["performanceAttributes"]

    def test_on_status_completed_has_model_name(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            assert "model" in perf["performanceAttributes"]

    def test_on_status_completed_has_result(self):
        cb = make_on_status_completed_callback("txn-001")
        for perf in cb["message"]["contract"]["performance"]:
            assert "result" in perf["performanceAttributes"]


class TestCallbackStorageComplianceWithSpec:
    """After storing callbacks, the accumulated contract must still be spec-compliant."""

    def test_stored_on_select_preserves_consideration(self):
        cb = make_on_select_callback("txn-schema-001")
        bap_store.store_callback(cb["context"], cb["message"])
        contract = bap_store.get_transaction_contract("txn-schema-001")
        assert "consideration" in contract
        assert contract["consideration"][0]["price"]["currency"] == "INR"

    def test_stored_on_status_preserves_performance_attributes(self):
        bap_store.store_callback(
            make_context("on_confirm", txn_id="txn-schema-002"), {"contract": {}}
        )
        cb = make_on_status_completed_callback("txn-schema-002")
        bap_store.store_callback(cb["context"], cb["message"])
        contract = bap_store.get_transaction_contract("txn-schema-002")
        assert "@context" in contract["performance"][0]["performanceAttributes"]
