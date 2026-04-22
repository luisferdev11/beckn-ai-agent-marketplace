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
def clean_store():
    """Reset in-memory store before and after each test."""
    from app import store
    store._callbacks.clear()
    store._transactions.clear()
    yield
    store._callbacks.clear()
    store._transactions.clear()


ONIX_BAP_BASE = "http://onix-bap:8081"
_BECKN_ACTIONS = ("select", "init", "confirm", "status", "cancel", "discover", "track", "update", "rating", "support")


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
