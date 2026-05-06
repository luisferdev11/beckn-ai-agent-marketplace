import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    bpps_yaml = tmp_path / "bpps.yaml"
    bpps_yaml.write_text(
        """
bpps:
  - subscriber_id: bpp.example.com
    receiver_url: http://onix-bpp:8082/bpp/receiver
    name: General Tecla Industries
  - subscriber_id: bpp-serg.example.com
    receiver_url: http://onix-bpp-serg:8083/bpp/receiver
    name: Serg Ops
"""
    )
    monkeypatch.setenv("DISCOVERY_CONFIG_PATH", str(bpps_yaml))

    # Re-import to pick up env var
    import importlib

    import app.main as discovery_main

    importlib.reload(discovery_main)

    return discovery_main.app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def discover_payload():
    return {
        "context": {
            "domain": "ai-agents",
            "action": "discover",
            "version": "2.0.0",
            "bapId": "bap.example.com",
            "bapUri": "http://onix-bap:8081/bap/receiver",
            "transactionId": "txn-test-001",
            "messageId": "msg-test-001",
            "timestamp": "2026-05-05T00:00:00Z",
            "ttl": "PT10M",
            "networkId": "beckn.one/testnet",
        },
        "message": {
            "intent": {
                "descriptor": {"name": "code review"},
            }
        },
    }
