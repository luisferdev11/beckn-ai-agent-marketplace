"""
In-memory store for callbacks and contracts.

Iter 0: simple dict/list in RAM. Will migrate to SQLite or Redis.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# All callbacks received from ONIX
_callbacks: list[dict] = []

# Contracts indexed by transactionId
_transactions: dict[str, dict] = {}


def store_callback(context: dict, message: dict):
    """Store an incoming on_* callback."""
    action = context.get("action", "unknown")
    txn_id = context.get("transactionId", "unknown")

    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "action": action,
        "transactionId": txn_id,
        "context": context,
        "message": message,
    }
    _callbacks.append(entry)

    # Update transaction state
    if txn_id not in _transactions:
        _transactions[txn_id] = {"transactionId": txn_id, "callbacks": [], "status": "ACTIVE"}

    _transactions[txn_id]["callbacks"].append(action)
    _transactions[txn_id]["last_action"] = action
    _transactions[txn_id]["last_message"] = message

    logger.info(f"stored callback {action} [txn={txn_id[:8]}] — total: {len(_callbacks)}")


def get_all_callbacks() -> list[dict]:
    return _callbacks


def get_last_callback() -> dict | None:
    return _callbacks[-1] if _callbacks else None


def get_callbacks_count() -> int:
    return len(_callbacks)


def get_transaction(txn_id: str) -> dict | None:
    return _transactions.get(txn_id)


def get_all_transactions() -> list[dict]:
    return list(_transactions.values())
