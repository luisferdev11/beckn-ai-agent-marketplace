"""
In-memory store for callbacks and contracts.

Iter 0: simple dict/list in RAM. Will migrate to SQLite or Redis.

The store tracks transactions and accumulates contract data as callbacks
arrive (on_select adds consideration, on_init confirms terms, etc.).
This allows the BAP API to build init/confirm payloads dynamically
from stored on_select data instead of hardcoding values.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# All callbacks received from ONIX
_callbacks: list[dict] = []

# Transactions indexed by transactionId — accumulates contract state
_transactions: dict[str, dict] = {}


def store_callback(context: dict, message: dict):
    """Store an incoming on_* callback and update transaction state."""
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

    # Initialize transaction if new
    if txn_id not in _transactions:
        _transactions[txn_id] = {
            "transactionId": txn_id,
            "callbacks": [],
            "status": "ACTIVE",
            "contract": {},
        }

    txn = _transactions[txn_id]
    txn["callbacks"].append(action)
    txn["last_action"] = action
    txn["last_message"] = message

    # Accumulate contract data from each callback
    contract = message.get("contract", {})
    if contract:
        stored_contract = txn["contract"]

        if action == "on_select":
            # on_select brings: id, participants, commitments, consideration
            stored_contract["id"] = contract.get("id", stored_contract.get("id"))
            stored_contract["participants"] = contract.get("participants", stored_contract.get("participants", []))
            stored_contract["commitments"] = contract.get("commitments", stored_contract.get("commitments", []))
            stored_contract["consideration"] = contract.get("consideration", stored_contract.get("consideration", []))

        elif action == "on_init":
            # on_init may add/update performance and settlements
            stored_contract["performance"] = contract.get("performance", stored_contract.get("performance", []))
            stored_contract["settlements"] = contract.get("settlements", stored_contract.get("settlements", []))

        elif action == "on_confirm":
            # on_confirm activates the contract
            txn["status"] = "CONFIRMED"
            stored_contract["performance"] = contract.get("performance", stored_contract.get("performance", []))
            stored_contract["settlements"] = contract.get("settlements", stored_contract.get("settlements", []))

        elif action == "on_status":
            # on_status updates performance with execution results
            txn["status"] = "COMPLETED"
            stored_contract["performance"] = contract.get("performance", stored_contract.get("performance", []))

    logger.info(f"stored callback {action} [txn={txn_id[:8]}] — total: {len(_callbacks)}")


def get_all_callbacks() -> list[dict]:
    return _callbacks


def get_last_callback() -> dict | None:
    return _callbacks[-1] if _callbacks else None


def get_callbacks_count() -> int:
    return len(_callbacks)


def get_transaction(txn_id: str) -> dict | None:
    return _transactions.get(txn_id)


def get_transaction_contract(txn_id: str) -> dict:
    """Get the accumulated contract data for a transaction."""
    txn = _transactions.get(txn_id)
    if txn:
        return txn.get("contract", {})
    return {}


def get_all_transactions() -> list[dict]:
    return list(_transactions.values())
