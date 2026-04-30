"""
BAP store — PostgreSQL backed.

Delegates all storage to app.db.repository which uses asyncpg.
This module preserves the same function signatures so existing routes
and webhooks work without changes.
"""
from __future__ import annotations

from app.db import repository as db


async def store_callback(context: dict, message: dict):
    await db.store_callback(context, message)


async def get_all_callbacks() -> list[dict]:
    return await db.get_all_callbacks()


async def get_last_callback() -> dict | None:
    return await db.get_last_callback()


async def get_callbacks_count() -> int:
    return await db.get_callbacks_count()


async def get_transaction(txn_id: str) -> dict | None:
    return await db.get_transaction(txn_id)


async def get_transaction_contract(txn_id: str) -> dict:
    return await db.get_transaction_contract(txn_id)


async def get_all_transactions() -> list[dict]:
    return await db.get_all_transactions()
