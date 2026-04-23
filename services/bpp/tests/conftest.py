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


@pytest.fixture(autouse=True)
def clean_contracts():
    """Reset in-memory contract store before and after each test."""
    from app.handlers import beckn_actions
    beckn_actions._contracts.clear()
    yield
    beckn_actions._contracts.clear()


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
