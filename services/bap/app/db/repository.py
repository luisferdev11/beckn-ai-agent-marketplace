"""BAP database repository — callbacks and transaction state in PostgreSQL."""
from __future__ import annotations

import json
import logging
from beckn_models.db import get_pool

logger = logging.getLogger(__name__)


async def store_callback(context: dict, message: dict):
    """Store an incoming on_* callback and update transaction contract state."""
    pool = await get_pool()
    action = context.get("action", "unknown")
    txn_id = context.get("transactionId", "unknown")

    await pool.execute(
        "INSERT INTO callbacks (transaction_id, action, context, message) VALUES ($1,$2,$3,$4)",
        txn_id, action, json.dumps(context), json.dumps(message),
    )

    contract_data = message.get("contract", {})
    existing = await pool.fetchrow("SELECT * FROM contracts WHERE transaction_id = $1", txn_id)

    if not existing:
        contract_code = contract_data.get("id", f"contract-{txn_id[:8]}")
        await pool.execute(
            """INSERT INTO contracts (contract_code, transaction_id, status,
                   commitments, consideration, performance, settlements, participants)
               VALUES ($1,$2,'ACTIVE',$3,$4,$5,$6,$7)""",
            contract_code, txn_id,
            json.dumps(contract_data.get("commitments", [])),
            json.dumps(contract_data.get("consideration", [])),
            json.dumps(contract_data.get("performance", [])),
            json.dumps(contract_data.get("settlements", [])),
            json.dumps(contract_data.get("participants", [])),
        )
    else:
        updates = {}
        if action == "on_select":
            if contract_data.get("id"):
                updates["contract_code"] = contract_data["id"]
            if contract_data.get("commitments"):
                updates["commitments"] = contract_data["commitments"]
            if contract_data.get("consideration"):
                updates["consideration"] = contract_data["consideration"]
            if contract_data.get("participants"):
                updates["participants"] = contract_data["participants"]
        elif action in ("on_init", "on_confirm"):
            if contract_data.get("performance"):
                updates["performance"] = contract_data["performance"]
            if contract_data.get("settlements"):
                updates["settlements"] = contract_data["settlements"]
            if action == "on_confirm":
                updates["status"] = "CONFIRMED"
        elif action == "on_status":
            if contract_data.get("performance"):
                updates["performance"] = contract_data["performance"]
            updates["status"] = "COMPLETED"

        if updates:
            sets = []
            vals = []
            i = 1
            json_fields = {"commitments", "consideration", "performance", "settlements", "participants"}
            for key, val in updates.items():
                sets.append(f"{key} = ${i}")
                vals.append(json.dumps(val) if key in json_fields else val)
                i += 1
            vals.append(txn_id)
            await pool.execute(
                f"UPDATE contracts SET {', '.join(sets)} WHERE transaction_id = ${i}",
                *vals,
            )

    logger.info(f"stored callback {action} [txn={txn_id[:8]}]")


async def get_all_callbacks():
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM callbacks ORDER BY received_at DESC LIMIT 200")
    return [dict(r) for r in rows]


async def get_last_callback():
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM callbacks ORDER BY received_at DESC LIMIT 1")
    return dict(row) if row else None


async def get_callbacks_count():
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM callbacks")
    return row["cnt"]


async def get_transaction(txn_id: str):
    pool = await get_pool()
    contract = await pool.fetchrow("SELECT * FROM contracts WHERE transaction_id = $1", txn_id)
    if not contract:
        return None
    callbacks = await pool.fetch(
        "SELECT action, received_at FROM callbacks WHERE transaction_id = $1 ORDER BY received_at",
        txn_id,
    )
    result = dict(contract)
    result["callbacks"] = [dict(c) for c in callbacks]
    return result


async def get_transaction_contract(txn_id: str) -> dict:
    """Get accumulated contract data for building Beckn payloads."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM contracts WHERE transaction_id = $1", txn_id)
    if not row:
        return {}
    r = dict(row)
    contract = {
        "id": r.get("contract_code", ""),
        "commitments": json.loads(r["commitments"]) if isinstance(r["commitments"], str) else r["commitments"],
        "consideration": json.loads(r["consideration"]) if isinstance(r["consideration"], str) else r["consideration"],
        "performance": json.loads(r["performance"]) if isinstance(r["performance"], str) else r["performance"],
        "settlements": json.loads(r["settlements"]) if isinstance(r["settlements"], str) else r["settlements"],
        "participants": json.loads(r["participants"]) if isinstance(r["participants"], str) else r["participants"],
    }
    return contract


async def get_all_transactions():
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM contracts ORDER BY created_at DESC LIMIT 100")
    return [dict(r) for r in rows]
