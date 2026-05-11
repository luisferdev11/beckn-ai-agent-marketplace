"""
Regression tests for issue #12 — phantom contracts from orphan callbacks.

Bug: a POST to /api/contracts/status (or init/confirm/cancel) with an
unknown transaction_id used to forward to ONIX, get a callback back, and
the callback handler would INSERT a fake row in `contracts` with
status='ACTIVE'. These tests pin the two invariants that fix it:

  1. API rejects unknown transactions with 404 before touching ONIX.
  2. `store_callback` for an unknown txn records the callback in the audit
     log but does NOT materialize a contract row.
"""

import pytest
from tests.factories.beckn import (
    make_on_select_callback,
    make_on_confirm_callback,
    make_on_status_completed_callback,
)
from app import store as bap_store


UNKNOWN_TXN = "txn-never-seen-by-select-00000"


class TestApiRejectsOrphanActions:
    @pytest.mark.parametrize("action", ["init", "confirm", "status", "cancel"])
    async def test_unknown_txn_returns_404(self, client, mock_onix, action):
        response = await client.post(
            f"/api/contracts/{action}",
            json={"transaction_id": UNKNOWN_TXN},
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("action", ["init", "confirm", "status", "cancel"])
    async def test_unknown_txn_does_not_reach_onix(self, client, mock_onix, action):
        await client.post(
            f"/api/contracts/{action}",
            json={"transaction_id": UNKNOWN_TXN},
        )
        assert not mock_onix[action].called, (
            f"{action} reached ONIX despite unknown transaction — "
            "the API-level guard is not active"
        )

    @pytest.mark.parametrize("action", ["init", "confirm", "status", "cancel"])
    async def test_unknown_txn_does_not_create_phantom_row(
        self, client, mock_onix, fake_db, action
    ):
        await client.post(
            f"/api/contracts/{action}",
            json={"transaction_id": UNKNOWN_TXN},
        )
        assert UNKNOWN_TXN not in fake_db["contracts"], (
            f"{action} on unknown txn materialized a phantom contract row"
        )


class TestStoreCallbackDoesNotCreateOrphans:
    """Defense-in-depth: even if a callback bypasses the API guard (e.g. a
    BPP sends an unsolicited on_*), store_callback must not create rows.
    """

    @pytest.mark.parametrize("factory", [
        make_on_select_callback,
        make_on_confirm_callback,
        make_on_status_completed_callback,
    ])
    async def test_orphan_callback_skips_contract_insert(self, fake_db, factory):
        cb = factory("txn-orphan-001")
        await bap_store.store_callback(cb["context"], cb["message"])
        assert "txn-orphan-001" not in fake_db["contracts"]

    @pytest.mark.parametrize("factory", [
        make_on_select_callback,
        make_on_confirm_callback,
        make_on_status_completed_callback,
    ])
    async def test_orphan_callback_is_still_audited(self, fake_db, factory):
        """The orphan is logged to the `callbacks` table — we don't drop
        evidence, we just don't pretend it represents a real contract."""
        cb = factory("txn-orphan-002")
        await bap_store.store_callback(cb["context"], cb["message"])
        assert len(fake_db["callbacks"]) == 1
        assert fake_db["callbacks"][0]["transaction_id"] == "txn-orphan-002"


class TestStoreCallbackUpdatesExistingContract:
    """When the contract exists (legitimate select happened), callbacks
    should still update fields as before — this guards against a too-
    aggressive fix that would also skip legitimate updates.
    """

    async def test_on_select_updates_existing_contract(self, fake_db, seeded_txn, client, mock_onix):
        txn_id = await seeded_txn("txn-real-001")
        cb = make_on_select_callback(txn_id)
        await bap_store.store_callback(cb["context"], cb["message"])
        # consideration is populated by the on_select factory
        assert len(fake_db["contracts"][txn_id]["consideration"]) > 0

    async def test_on_confirm_transitions_to_active(self, fake_db, seeded_txn, client, mock_onix):
        txn_id = await seeded_txn("txn-real-002")
        cb = make_on_confirm_callback(txn_id)
        await bap_store.store_callback(cb["context"], cb["message"])
        assert fake_db["contracts"][txn_id]["status"] == "ACTIVE"

    async def test_on_status_transitions_to_completed(self, fake_db, seeded_txn, client, mock_onix):
        txn_id = await seeded_txn("txn-real-003")
        await bap_store.store_callback(*_cb(make_on_confirm_callback(txn_id)))
        await bap_store.store_callback(*_cb(make_on_status_completed_callback(txn_id)))
        assert fake_db["contracts"][txn_id]["status"] == "COMPLETED"


def _cb(cb_dict):
    return cb_dict["context"], cb_dict["message"]
