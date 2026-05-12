"""
BPP test fixtures.

The BPP repository normally talks to PostgreSQL via asyncpg. For unit and
integration tests we replace the repository functions with an in-memory
implementation so tests stay fast and offline. Real DB behavior is covered
by the E2E suite (tests/e2e/).
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
import respx as respx_lib


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _seed_agent(db_id: int, beckn_id: str, label: str, unit_price: float) -> dict:
    return {
        "id": db_id,
        "beckn_id": beckn_id,
        "label": label,
        "access_point_url": "http://agents:3004",
        "pricing_model": {"value": unit_price, "currency": "INR"},
        "sla": {"maxLatencyMs": 10000},
        "status": "active",
        "agent_name": {"en": label},
        "description": f"{label} test agent",
        "provider_id": 1,
        "provider_org": {"name": "Test Provider"},
        "subscriber_id": "bpp.example.com",
        "category_name": "ai_agent",
        "capabilities": {},
        "skills": [],
        "input_schema": {},
        "output_schema": {},
        "endpoints": {"static": []},
    }


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    """In-memory replacement for app.db.repository.

    Monkeypatches the 6 repository functions the handlers invoke so tests
    don't need Postgres. The seeded agent catalog matches the pricing
    expectations of test_pricing.py:
        agent-summarizer-001     → 6.00 INR
        agent-code-reviewer-001  → 10.00 INR
        agent-data-extractor-001 → 4.00 INR

    Yields a handle so tests can inspect or seed state:
        fake_db['contracts']  — dict[transaction_id, contract_row]
        fake_db['agents']     — dict[beckn_id, agent_row]
    """
    contracts: dict[str, dict] = {}
    agents: dict[str, dict] = {
        "agent-summarizer-001": _seed_agent(1, "agent-summarizer-001", "Summarizer", 6.0),
        "agent-code-reviewer-001": _seed_agent(2, "agent-code-reviewer-001", "Code Reviewer", 10.0),
        "agent-data-extractor-001": _seed_agent(3, "agent-data-extractor-001", "Data Extractor", 4.0),
    }

    async def _search_agents(keywords):
        results = []
        for a in agents.values():
            if a["status"] != "active":
                continue
            blob = (
                str(a.get("capabilities", ""))
                + str(a.get("skills", ""))
                + str(a.get("agent_name", ""))
                + str(a.get("description", ""))
            ).lower()
            if any(kw.lower() in blob for kw in keywords):
                results.append(a)
        return results

    async def _list_agents():
        return list(agents.values())

    async def _get_agent_by_beckn_id(beckn_id):
        return agents.get(beckn_id)

    async def _create_contract(contract_code, transaction_id, **kwargs):
        if transaction_id in contracts:
            # Mimics ON CONFLICT (transaction_id) DO UPDATE SET status, commitments, consideration
            row = contracts[transaction_id]
            row["status"] = kwargs.get("status", row["status"])
            if "commitments" in kwargs:
                row["commitments"] = kwargs["commitments"]
            if "consideration" in kwargs:
                row["consideration"] = kwargs["consideration"]
            return row
        row = {
            "contract_code": contract_code,
            "transaction_id": transaction_id,
            "agent_id": kwargs.get("agent_id"),
            "provider_id": kwargs.get("provider_id"),
            "bap_id": kwargs.get("bap_id"),
            "bpp_id": kwargs.get("bpp_id"),
            "status": kwargs.get("status", "DRAFT"),
            "commitments": kwargs.get("commitments", []),
            "consideration": kwargs.get("consideration", []),
            "performance": kwargs.get("performance", []),
            "settlements": kwargs.get("settlements", []),
            "participants": kwargs.get("participants", []),
            "total_amount": kwargs.get("total_amount"),
            "currency": kwargs.get("currency", "INR"),
            "execution_id": None,
        }
        contracts[transaction_id] = row
        return row

    async def _get_contract_by_txn(transaction_id):
        return contracts.get(transaction_id)

    async def _update_contract(transaction_id, **kwargs):
        if transaction_id not in contracts:
            return None
        contracts[transaction_id].update(kwargs)
        return contracts[transaction_id]

    from app.db import repository
    monkeypatch.setattr(repository, "search_agents", _search_agents)
    monkeypatch.setattr(repository, "list_agents", _list_agents)
    monkeypatch.setattr(repository, "get_agent_by_beckn_id", _get_agent_by_beckn_id)
    monkeypatch.setattr(repository, "create_contract", _create_contract)
    monkeypatch.setattr(repository, "get_contract_by_txn", _get_contract_by_txn)
    monkeypatch.setattr(repository, "update_contract", _update_contract)

    yield {"contracts": contracts, "agents": agents}

    contracts.clear()


@pytest.fixture
def mock_orchestrator():
    """
    Mock orchestrator client calls.
    BPP calls start_execution on confirm and get_execution on status.
    """
    with patch("app.handlers.orchestrator_client.start_execution", new_callable=AsyncMock) as mock_start, \
         patch("app.handlers.orchestrator_client.get_execution", new_callable=AsyncMock) as mock_get:
        mock_start.return_value = {"execution_id": "exec-test-001"}
        mock_get.return_value = {
            "status": "COMPLETED",
            "result": {"review": "Code looks good. No critical issues found."},
            "metadata": {
                "started_at": "2026-04-22T00:00:00.000Z",
                "completed_at": "2026-04-22T00:00:01.500Z",
                "latency_ms": 1500,
                "tokens_used": {"input": 109, "output": 523, "total": 632},
                "model": "llama-3.3-70b-versatile",
            },
        }
        yield mock_start, mock_get


@pytest.fixture
def mock_onix_bpp():
    """
    Mock ONIX-BPP caller — intercepts on_* callbacks.
    The BPP sends on_* responses to http://onix-bpp:8082/bpp/caller/on_{action}.
    """
    with respx_lib.mock(base_url="http://onix-bpp:8082", assert_all_called=False) as mock:
        ack = {"message": {"ack": {"status": "ACK"}}}
        mock.post(path__regex=r"/bpp/caller/on_.*").respond(200, json=ack)
        yield mock
