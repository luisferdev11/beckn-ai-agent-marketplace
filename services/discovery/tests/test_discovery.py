"""
Discovery Service tests.

Covers:
  - Health and registry endpoints expose the configured BPPs
  - POST /beckn/discover returns ACK synchronously
  - Discover triggers fan-out to every registered BPP receiver
  - One BPP failing does not block the other (best-effort)
"""
import asyncio

import pytest
import respx
from httpx import Response


class TestHealthAndRegistry:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_health_reports_bpp_count(self, client):
        resp = await client.get("/health")
        assert resp.json()["bpps"] == 2

    async def test_bpps_list_contains_both_providers(self, client):
        resp = await client.get("/bpps")
        body = resp.json()
        assert body["count"] == 2
        names = {b["name"] for b in body["bpps"]}
        assert names == {"General Tecla Industries", "Serg Ops"}


class TestDiscoverEndpoint:
    async def test_returns_ack_sync(self, client, discover_payload):
        with respx.mock(assert_all_called=False) as mock:
            mock.post(path__regex=r".*/discover$").respond(200, json={"message": {"ack": {"status": "ACK"}}})
            resp = await client.post("/beckn/discover", json=discover_payload)
        assert resp.status_code == 200
        assert resp.json()["message"]["ack"]["status"] == "ACK"

    async def test_fans_out_to_both_bpps(self, client, discover_payload):
        with respx.mock(assert_all_called=False) as mock:
            tecla = mock.post("http://onix-bpp:8082/bpp/receiver/discover").respond(
                200, json={"message": {"ack": {"status": "ACK"}}}
            )
            serg = mock.post("http://onix-bpp-serg:8083/bpp/receiver/discover").respond(
                200, json={"message": {"ack": {"status": "ACK"}}}
            )
            await client.post("/beckn/discover", json=discover_payload)
            # background_tasks runs after response is returned but before app exits the request
            await asyncio.sleep(0.2)
        assert tecla.called, "Tecla BPP receiver was not called"
        assert serg.called, "Serg BPP receiver was not called"

    async def test_one_bpp_failure_doesnt_block_the_other(self, client, discover_payload):
        with respx.mock(assert_all_called=False) as mock:
            tecla = mock.post("http://onix-bpp:8082/bpp/receiver/discover").respond(500, json={"err": "boom"})
            serg = mock.post("http://onix-bpp-serg:8083/bpp/receiver/discover").respond(
                200, json={"message": {"ack": {"status": "ACK"}}}
            )
            resp = await client.post("/beckn/discover", json=discover_payload)
            await asyncio.sleep(0.2)
        # Caller still gets ACK
        assert resp.status_code == 200
        # Both were attempted
        assert tecla.called
        assert serg.called

    async def test_forwards_authorization_header(self, client, discover_payload):
        with respx.mock(assert_all_called=False) as mock:
            tecla = mock.post("http://onix-bpp:8082/bpp/receiver/discover").respond(
                200, json={"message": {"ack": {"status": "ACK"}}}
            )
            mock.post("http://onix-bpp-serg:8083/bpp/receiver/discover").respond(
                200, json={"message": {"ack": {"status": "ACK"}}}
            )
            await client.post(
                "/beckn/discover",
                json=discover_payload,
                headers={"Authorization": "Signature keyId=\"bap.example.com|key1|ed25519\""},
            )
            await asyncio.sleep(0.2)
        assert tecla.called
        last_call = tecla.calls.last
        assert "authorization" in {h.lower() for h in last_call.request.headers.keys()}


class TestEmptyConfig:
    async def test_no_bpps_configured_still_acks(self, monkeypatch, tmp_path, discover_payload):
        empty = tmp_path / "empty.yaml"
        empty.write_text("bpps: []\n")
        monkeypatch.setenv("DISCOVERY_CONFIG_PATH", str(empty))

        import importlib

        import app.main as discovery_main

        importlib.reload(discovery_main)

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=discovery_main.app), base_url="http://test") as c:
            resp = await c.post("/beckn/discover", json=discover_payload)
        assert resp.status_code == 200
        assert resp.json()["message"]["ack"]["status"] == "ACK"
