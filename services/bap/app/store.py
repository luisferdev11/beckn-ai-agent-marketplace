"""
BAP store — PostgreSQL backed.

Delegates persistent storage to app.db.repository which uses asyncpg.
This module preserves the same function signatures so existing routes
and webhooks work without changes.

In-memory layer (transaction targets):
  Tracks which BPP each transaction is talking to. After a federated
  discover the BAP gets multiple on_discover responses (one per BPP);
  when it picks a specific agent in select, init/confirm/status must
  route back to the same BPP. The mapping lives in process memory
  because it's pure routing metadata — losing it on restart is fine,
  the transaction can simply be retried. If we ever need cross-process
  coherence we can move this to a small `transaction_targets` table.
"""
from __future__ import annotations

from app.db import repository as db


async def store_callback(context: dict, message: dict, error: dict | None = None):
    await db.store_callback(context, message, error)


async def create_draft_contract(
    txn_id: str,
    contract_code: str,
    commitments: list | None = None,
    participants: list | None = None,
) -> bool:
    return await db.create_draft_contract(txn_id, contract_code, commitments, participants)


async def contract_exists(txn_id: str) -> bool:
    return await db.contract_exists(txn_id)


async def get_all_callbacks() -> list[dict]:
    return await db.get_all_callbacks()


async def get_last_callback(transaction_id: str | None = None) -> dict | None:
    return await db.get_last_callback(transaction_id)


async def get_callbacks_count(transaction_id: str | None = None) -> int:
    return await db.get_callbacks_count(transaction_id)


async def get_transaction(txn_id: str) -> dict | None:
    return await db.get_transaction(txn_id)


async def get_transaction_contract(txn_id: str) -> dict:
    return await db.get_transaction_contract(txn_id)


async def get_all_transactions() -> list[dict]:
    return await db.get_all_transactions()


# ── In-memory transaction target tracking (BPP routing) ─────────────────────

_transaction_targets: dict[str, dict[str, str]] = {}


def set_transaction_target(txn_id: str, bpp_id: str, bpp_uri: str) -> None:
    """Record which BPP a transaction is targeting (set on select)."""
    _transaction_targets[txn_id] = {"bpp_id": bpp_id, "bpp_uri": bpp_uri}


def get_transaction_target(txn_id: str) -> dict[str, str]:
    """Return the BPP target recorded for a transaction (empty if unknown)."""
    return _transaction_targets.get(txn_id, {})
