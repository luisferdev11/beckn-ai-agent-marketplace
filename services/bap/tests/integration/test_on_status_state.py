"""
Integration tests for BAP repository: contract.status transitions on on_status.

Regression for issue #16 — on_status used to set contract.status='COMPLETED'
unconditionally, even when performance[0].status.code was RUNNING/PENDING.
The contract status must reflect the execution status carried in the payload.
"""

import pytest
from tests.factories.beckn import (
    make_on_confirm_callback,
    make_on_status_completed_callback,
    make_on_status_failed_callback,
    make_on_status_pending_callback,
)
from app import store as bap_store


def _cb(cb_dict):
    return cb_dict["context"], cb_dict["message"]


class TestOnStatusReflectsExecutionState:
    async def test_pending_status_keeps_contract_active(self, seeded_txn, fake_db):
        """A RUNNING execution must NOT promote the contract to COMPLETED."""
        txn_id = await seeded_txn("txn-status-pending-001")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_pending_callback(txn_id)))

        assert fake_db["contracts"][txn_id]["status"] == "ACTIVE"

    async def test_completed_status_promotes_to_completed(self, seeded_txn, fake_db):
        txn_id = await seeded_txn("txn-status-completed-001")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_completed_callback(txn_id)))

        assert fake_db["contracts"][txn_id]["status"] == "COMPLETED"

    async def test_failed_status_marks_contract_failed(self, seeded_txn, fake_db):
        txn_id = await seeded_txn("txn-status-failed-001")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_failed_callback(txn_id)))

        assert fake_db["contracts"][txn_id]["status"] == "FAILED"

    async def test_pending_then_completed_ends_completed(self, seeded_txn, fake_db):
        """Real-world polling: multiple on_status arrive; only the terminal
        one promotes the contract."""
        txn_id = await seeded_txn("txn-status-sequence-001")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_pending_callback(txn_id)))
        assert fake_db["contracts"][txn_id]["status"] == "ACTIVE"

        await bap_store.store_callback(*_cb(make_on_status_completed_callback(txn_id)))
        assert fake_db["contracts"][txn_id]["status"] == "COMPLETED"

    async def test_on_status_still_stores_performance_when_pending(self, seeded_txn, fake_db):
        """Even when not terminal, the performance block must be recorded so
        the UI can show progress data."""
        txn_id = await seeded_txn("txn-status-perf-001")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_pending_callback(txn_id)))

        perf = fake_db["contracts"][txn_id]["performance"]
        assert perf and perf[0]["status"]["code"] == "RUNNING"
