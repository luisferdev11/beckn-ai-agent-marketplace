"""
BAP test fixtures.

The BAP repository normally talks to PostgreSQL via asyncpg. For unit and
integration tests we replace the repository functions with an in-memory
implementation so tests stay fast and offline. Real DB behavior is covered
by the E2E suite (tests/e2e/).
"""
import pytest
from httpx import AsyncClient, ASGITransport
import respx as respx_lib


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    """In-memory replacement for app.db.repository.

    Monkeypatches every repository function so tests don't need Postgres.
    The wiring in app/store.py does `db.create_draft_contract(...)` — the
    lookup happens at call time, so patching the module attributes works.

    Yields a handle with two collections so tests can inspect or seed state:
        fake_db['contracts']      — dict[txn_id, contract_row]
        fake_db['callbacks']      — list[callback_row]
        fake_db['ratings_sent']   — list[rating_row]
    """
    contracts: dict[str, dict] = {}
    callbacks: list[dict] = []
    ratings_sent: list[dict] = []

    def _empty_contract(txn_id: str, contract_code: str) -> dict:
        return {
            "contract_code": contract_code,
            "transaction_id": txn_id,
            "status": "DRAFT",
            "commitments": [],
            "consideration": [],
            "performance": [],
            "settlements": [],
            "participants": [],
        }

    async def _create_draft_contract(txn_id, contract_code, commitments=None, participants=None):
        if txn_id in contracts:
            return False
        row = _empty_contract(txn_id, contract_code)
        row["commitments"] = commitments or []
        row["participants"] = participants or []
        contracts[txn_id] = row
        return True

    async def _contract_exists(txn_id):
        return txn_id in contracts

    async def _store_callback(context, message, error=None):
        action = context.get("action", "unknown")
        txn_id = context.get("transactionId", "unknown")
        callbacks.append({
            "transaction_id": txn_id,
            "action": action,
            "context": context,
            "message": message,
            "error": error,
        })

        if txn_id not in contracts:
            # Orphan callback — recorded in audit log only. See issue #12.
            return

        row = contracts[txn_id]
        contract_data = message.get("contract", {})

        if action == "on_select":
            if contract_data.get("id"):
                row["contract_code"] = contract_data["id"]
            if contract_data.get("commitments"):
                row["commitments"] = contract_data["commitments"]
            if contract_data.get("consideration"):
                row["consideration"] = contract_data["consideration"]
            if contract_data.get("participants"):
                row["participants"] = contract_data["participants"]
        elif action in ("on_init", "on_confirm"):
            if contract_data.get("performance"):
                row["performance"] = contract_data["performance"]
            if contract_data.get("settlements"):
                row["settlements"] = contract_data["settlements"]
            if action == "on_confirm":
                row["status"] = "ACTIVE"
        elif action == "on_status":
            if contract_data.get("performance"):
                row["performance"] = contract_data["performance"]
            perf = contract_data.get("performance") or []
            exec_code = perf[0].get("status", {}).get("code", "") if perf else ""
            if exec_code == "COMPLETED":
                row["status"] = "COMPLETED"
            elif exec_code == "FAILED":
                row["status"] = "FAILED"

    async def _get_transaction_contract(txn_id):
        if txn_id not in contracts:
            return {}
        c = contracts[txn_id]
        return {
            "id": c.get("contract_code", ""),
            "commitments": c.get("commitments", []),
            "consideration": c.get("consideration", []),
            "performance": c.get("performance", []),
            "settlements": c.get("settlements", []),
            "participants": c.get("participants", []),
        }

    async def _get_transaction(txn_id):
        if txn_id not in contracts:
            return None
        result = dict(contracts[txn_id])
        result["callbacks"] = [
            {"action": cb["action"]} for cb in callbacks if cb["transaction_id"] == txn_id
        ]
        return result

    async def _get_all_callbacks():
        return list(reversed(callbacks))

    async def _get_last_callback(transaction_id=None):
        for cb in reversed(callbacks):
            if transaction_id is None or cb["transaction_id"] == transaction_id:
                return cb
        return None

    async def _get_callbacks_count(transaction_id=None):
        if transaction_id is None:
            return len(callbacks)
        return sum(1 for cb in callbacks if cb["transaction_id"] == transaction_id)

    async def _get_all_transactions():
        return list(contracts.values())

    async def _record_rating_sent(*, transaction_id, target_id, target_type,
                                  score, score_min, score_max, feedback, bpp_id):
        # Upsert: replace existing row with the same (txn, target, type).
        for row in ratings_sent:
            if (row["transaction_id"] == transaction_id
                    and row["target_id"] == target_id
                    and row["target_type"] == target_type):
                row.update({
                    "score": score, "score_min": score_min, "score_max": score_max,
                    "feedback": feedback, "bpp_id": bpp_id,
                })
                return row
        new_row = {
            "id": len(ratings_sent) + 1,
            "transaction_id": transaction_id,
            "target_id": target_id,
            "target_type": target_type,
            "score": score, "score_min": score_min, "score_max": score_max,
            "feedback": feedback, "bpp_id": bpp_id,
        }
        ratings_sent.append(new_row)
        return new_row

    from app.db import repository
    monkeypatch.setattr(repository, "create_draft_contract", _create_draft_contract)
    monkeypatch.setattr(repository, "contract_exists", _contract_exists)
    monkeypatch.setattr(repository, "store_callback", _store_callback)
    monkeypatch.setattr(repository, "get_transaction_contract", _get_transaction_contract)
    monkeypatch.setattr(repository, "get_transaction", _get_transaction)
    monkeypatch.setattr(repository, "get_all_callbacks", _get_all_callbacks)
    monkeypatch.setattr(repository, "get_last_callback", _get_last_callback)
    monkeypatch.setattr(repository, "get_callbacks_count", _get_callbacks_count)
    monkeypatch.setattr(repository, "get_all_transactions", _get_all_transactions)
    monkeypatch.setattr(repository, "record_rating_sent", _record_rating_sent, raising=False)

    # Reset the in-memory transaction-target map between tests.
    from app import store as _store
    _store._transaction_targets.clear()

    yield {
        "contracts": contracts,
        "callbacks": callbacks,
        "ratings_sent": ratings_sent,
    }

    contracts.clear()
    callbacks.clear()
    ratings_sent.clear()
    _store._transaction_targets.clear()


ONIX_BAP_BASE = "http://onix-bap:8081"
_BECKN_ACTIONS = ("select", "init", "confirm", "status", "cancel", "discover", "track", "update", "rate", "rating", "support")


@pytest.fixture
def mock_onix():
    """
    Mock ONIX-BAP caller — returns ACK for any Beckn action.
    The BAP sends requests to http://onix-bap:8081/bap/caller/{action}.

    Yields a dict {action: respx_route} so tests can assert on calls:
        mock_onix["select"].called
        json.loads(mock_onix["select"].calls.last.request.content)
    """
    ack = {"message": {"ack": {"status": "ACK"}}}
    routes = {}
    with respx_lib.mock(assert_all_called=False) as mock:
        for action in _BECKN_ACTIONS:
            routes[action] = mock.post(f"{ONIX_BAP_BASE}/bap/caller/{action}").respond(200, json=ack)
        yield routes


@pytest.fixture
def mock_onix_nack():
    """Mock ONIX returning NACK — simulates validation or signature error."""
    nack = {"message": {"ack": {"status": "NACK"}}, "error": {"code": "CORE-001", "message": "Invalid signature"}}
    with respx_lib.mock(assert_all_called=False) as mock:
        for action in _BECKN_ACTIONS:
            mock.post(f"{ONIX_BAP_BASE}/bap/caller/{action}").respond(200, json=nack)
        yield mock


@pytest.fixture
async def seeded_txn(client, mock_onix, fake_db):
    """Helper: run a real /select call and return the transaction_id.

    Many tests for init/confirm/status/cancel need a pre-existing contract row.
    The cleanest setup is to drive it through the actual select endpoint so
    the DRAFT row + the transaction_target are both populated.
    """
    async def _seed(txn_id: str = None, agent_id: str = "agent-summarizer-001") -> str:
        body = {"agent_id": agent_id, "offer_id": "offer-summarizer-basic"}
        if txn_id:
            body["transaction_id"] = txn_id
        resp = await client.post("/api/contracts/select", json=body)
        assert resp.status_code == 200
        return resp.json()["transactionId"]
    return _seed
