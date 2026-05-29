"""Webhook robustness against malformed inputs (BPP-Serg).

Mirrors ``services/bpp/tests/integration/test_error_handling.py``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def malformed_json_body() -> str:
    return '{not valid json'


class TestMalformedJsonReturnsNack:
    async def test_malformed_select_returns_400(self, client, malformed_json_body):
        resp = await client.post(
            "/api/webhook/select",
            content=malformed_json_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_malformed_select_returns_beckn_nack_envelope(
        self, client, malformed_json_body
    ):
        resp = await client.post(
            "/api/webhook/select",
            content=malformed_json_body,
            headers={"Content-Type": "application/json"},
        )
        body = resp.json()
        assert body["message"]["ack"]["status"] == "NACK"
        assert body["error"].get("code")

    async def test_empty_body_also_nacks(self, client):
        resp = await client.post(
            "/api/webhook/select",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"]["ack"]["status"] == "NACK"
