"""
Unit tests for BAP in-memory store.

The store accumulates Beckn callbacks and builds up the contract state.
These tests ensure the accumulation logic is correct regardless of the
underlying persistence technology (in-memory today, PostgreSQL tomorrow).
"""

import pytest
from tests.factories.beckn import make_context


def _store():
    from app import store
    return store


class TestStoreCallback:
    def test_creates_transaction_on_first_callback(self):
        s = _store()
        ctx = make_context("on_select", txn_id="txn-001")
        s.store_callback(ctx, {"contract": {}})
        assert s.get_transaction("txn-001") is not None

    def test_callback_is_stored_in_list(self):
        s = _store()
        ctx = make_context("on_select", txn_id="txn-001")
        s.store_callback(ctx, {})
        assert s.get_callbacks_count() == 1

    def test_multiple_callbacks_accumulated(self):
        s = _store()
        for action in ("on_select", "on_init", "on_confirm"):
            s.store_callback(make_context(action, txn_id="txn-001"), {})
        txn = s.get_transaction("txn-001")
        assert txn["callbacks"] == ["on_select", "on_init", "on_confirm"]

    def test_last_callback_retrievable(self):
        s = _store()
        s.store_callback(make_context("on_select", txn_id="txn-001"), {"msg": "first"})
        s.store_callback(make_context("on_init", txn_id="txn-001"), {"msg": "second"})
        last = s.get_last_callback()
        assert last["action"] == "on_init"

    def test_get_unknown_transaction_returns_none(self):
        assert _store().get_transaction("does-not-exist") is None

    def test_get_unknown_contract_returns_empty_dict(self):
        assert _store().get_transaction_contract("does-not-exist") == {}


class TestContractAccumulation:
    def test_on_select_stores_commitments(self):
        s = _store()
        commitments = [{"id": "commitment-001", "status": {"code": "DRAFT"}}]
        ctx = make_context("on_select", txn_id="txn-002")
        s.store_callback(ctx, {"contract": {"commitments": commitments, "consideration": []}})
        contract = s.get_transaction_contract("txn-002")
        assert contract["commitments"] == commitments

    def test_on_select_stores_consideration(self):
        s = _store()
        consideration = [{"id": "c-001", "price": {"currency": "INR", "value": "7.08"}}]
        ctx = make_context("on_select", txn_id="txn-003")
        s.store_callback(ctx, {"contract": {"consideration": consideration}})
        contract = s.get_transaction_contract("txn-003")
        assert contract["consideration"] == consideration

    def test_on_init_stores_performance_and_settlements(self):
        s = _store()
        s.store_callback(make_context("on_select", txn_id="txn-004"), {"contract": {}})
        performance = [{"id": "perf-001"}]
        settlements = [{"id": "settlement-001", "status": "DRAFT"}]
        s.store_callback(make_context("on_init", txn_id="txn-004"), {
            "contract": {"performance": performance, "settlements": settlements}
        })
        contract = s.get_transaction_contract("txn-004")
        assert contract["performance"] == performance
        assert contract["settlements"] == settlements

    def test_on_confirm_sets_transaction_status_confirmed(self):
        s = _store()
        s.store_callback(make_context("on_select", txn_id="txn-005"), {"contract": {}})
        s.store_callback(make_context("on_confirm", txn_id="txn-005"), {"contract": {}})
        txn = s.get_transaction("txn-005")
        assert txn["status"] == "CONFIRMED"

    def test_on_status_sets_transaction_status_completed(self):
        s = _store()
        s.store_callback(make_context("on_select", txn_id="txn-006"), {"contract": {}})
        s.store_callback(make_context("on_confirm", txn_id="txn-006"), {"contract": {}})
        s.store_callback(make_context("on_status", txn_id="txn-006"), {
            "contract": {"performance": [{"id": "perf-001", "status": {"code": "COMPLETED"}}]}
        })
        txn = s.get_transaction("txn-006")
        assert txn["status"] == "COMPLETED"

    def test_contract_id_preserved_from_on_select(self):
        s = _store()
        ctx = make_context("on_select", txn_id="txn-007")
        s.store_callback(ctx, {"contract": {"id": "contract-abc123", "commitments": []}})
        contract = s.get_transaction_contract("txn-007")
        assert contract["id"] == "contract-abc123"

    def test_two_transactions_are_independent(self):
        s = _store()
        s.store_callback(make_context("on_select", txn_id="txn-A"), {
            "contract": {"consideration": [{"price": {"value": "7.08"}}]}
        })
        s.store_callback(make_context("on_select", txn_id="txn-B"), {
            "contract": {"consideration": [{"price": {"value": "11.80"}}]}
        })
        assert s.get_transaction_contract("txn-A")["consideration"][0]["price"]["value"] == "7.08"
        assert s.get_transaction_contract("txn-B")["consideration"][0]["price"]["value"] == "11.80"
