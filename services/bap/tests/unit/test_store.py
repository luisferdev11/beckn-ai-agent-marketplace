"""
Unit tests for BAP store callback accumulation.

Verify that, given a contract row already exists (created by /select),
incoming on_* callbacks accumulate state correctly — commitments,
consideration, performance, settlements, status transitions.

Orphan callback behavior (issue #12) lives in tests/integration/test_orphan_protection.py.
"""

import pytest
from tests.factories.beckn import make_context
from app import store as bap_store


async def _seed(txn_id: str):
    """Pre-create a DRAFT contract for the test txn — mimics what /select does."""
    await bap_store.create_draft_contract(txn_id, f"contract-{txn_id[:8]}")


class TestStoreCallback:
    async def test_callback_is_recorded(self, fake_db):
        await _seed("txn-001")
        ctx = make_context("on_select", txn_id="txn-001")
        await bap_store.store_callback(ctx, {"contract": {}})
        assert await bap_store.get_callbacks_count() == 1

    async def test_multiple_callbacks_accumulate(self, fake_db):
        await _seed("txn-001")
        for action in ("on_select", "on_init", "on_confirm"):
            await bap_store.store_callback(make_context(action, txn_id="txn-001"), {"contract": {}})
        txn = await bap_store.get_transaction("txn-001")
        actions = [cb["action"] for cb in txn["callbacks"]]
        assert actions == ["on_select", "on_init", "on_confirm"]

    async def test_last_callback_retrievable(self, fake_db):
        await _seed("txn-001")
        await bap_store.store_callback(make_context("on_select", txn_id="txn-001"), {"contract": {}})
        await bap_store.store_callback(make_context("on_init", txn_id="txn-001"), {"contract": {}})
        last = await bap_store.get_last_callback()
        assert last["action"] == "on_init"

    async def test_get_unknown_transaction_returns_none(self, fake_db):
        assert await bap_store.get_transaction("does-not-exist") is None

    async def test_get_unknown_contract_returns_empty_dict(self, fake_db):
        assert await bap_store.get_transaction_contract("does-not-exist") == {}


class TestContractAccumulation:
    async def test_on_select_stores_commitments(self, fake_db):
        await _seed("txn-002")
        commitments = [{"id": "commitment-001", "status": {"code": "DRAFT"}}]
        await bap_store.store_callback(
            make_context("on_select", txn_id="txn-002"),
            {"contract": {"commitments": commitments, "consideration": []}},
        )
        contract = await bap_store.get_transaction_contract("txn-002")
        assert contract["commitments"] == commitments

    async def test_on_select_stores_consideration(self, fake_db):
        await _seed("txn-003")
        consideration = [{"id": "c-001", "price": {"currency": "INR", "value": "7.08"}}]
        await bap_store.store_callback(
            make_context("on_select", txn_id="txn-003"),
            {"contract": {"consideration": consideration}},
        )
        contract = await bap_store.get_transaction_contract("txn-003")
        assert contract["consideration"] == consideration

    async def test_on_init_stores_performance_and_settlements(self, fake_db):
        await _seed("txn-004")
        await bap_store.store_callback(make_context("on_select", txn_id="txn-004"), {"contract": {}})
        performance = [{"id": "perf-001"}]
        settlements = [{"id": "settlement-001", "status": "DRAFT"}]
        await bap_store.store_callback(
            make_context("on_init", txn_id="txn-004"),
            {"contract": {"performance": performance, "settlements": settlements}},
        )
        contract = await bap_store.get_transaction_contract("txn-004")
        assert contract["performance"] == performance
        assert contract["settlements"] == settlements

    async def test_on_confirm_sets_status_active(self, fake_db):
        """on_confirm transitions the contract to ACTIVE. The CHECK constraint
        on contracts.status only allows DRAFT/ACTIVE/COMPLETED/FAILED/CANCELLED,
        so we don't use 'CONFIRMED' — see infra/db/migrations/001_schema.sql.
        """
        await _seed("txn-005")
        await bap_store.store_callback(make_context("on_confirm", txn_id="txn-005"), {"contract": {}})
        txn = await bap_store.get_transaction("txn-005")
        assert txn["status"] == "ACTIVE"

    async def test_on_status_sets_status_completed(self, fake_db):
        await _seed("txn-006")
        await bap_store.store_callback(make_context("on_confirm", txn_id="txn-006"), {"contract": {}})
        await bap_store.store_callback(
            make_context("on_status", txn_id="txn-006"),
            {"contract": {"performance": [{"id": "perf-001", "status": {"code": "COMPLETED"}}]}},
        )
        txn = await bap_store.get_transaction("txn-006")
        assert txn["status"] == "COMPLETED"

    async def test_contract_id_preserved_from_on_select(self, fake_db):
        await _seed("txn-007")
        await bap_store.store_callback(
            make_context("on_select", txn_id="txn-007"),
            {"contract": {"id": "contract-abc123", "commitments": []}},
        )
        contract = await bap_store.get_transaction_contract("txn-007")
        assert contract["id"] == "contract-abc123"

    async def test_two_transactions_are_independent(self, fake_db):
        await _seed("txn-A")
        await _seed("txn-B")
        await bap_store.store_callback(
            make_context("on_select", txn_id="txn-A"),
            {"contract": {"consideration": [{"price": {"value": "7.08"}}]}},
        )
        await bap_store.store_callback(
            make_context("on_select", txn_id="txn-B"),
            {"contract": {"consideration": [{"price": {"value": "11.80"}}]}},
        )
        a = await bap_store.get_transaction_contract("txn-A")
        b = await bap_store.get_transaction_contract("txn-B")
        assert a["consideration"][0]["price"]["value"] == "7.08"
        assert b["consideration"][0]["price"]["value"] == "11.80"
