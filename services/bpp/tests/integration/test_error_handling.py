"""
Webhook robustness against malformed inputs.

ONIX-BPP is the normal caller and always sends signed, schema-valid JSON.
But a misconfigured caller (or a probing request) can hit the webhook
with a body that is not JSON at all, or with `Content-Type: application/json`
but a body that does not parse. The default FastAPI behaviour is to let
``json.JSONDecodeError`` bubble up as a 500 — that is wrong on two counts:

  1. Beckn callers expect either a 2xx ACK or a 4xx NACK envelope; a 500
     is opaque and routes through ONIX as a transport error.
  2. The conformance kit (``scripts/bpp_conformance_kit.py``) treats the
     malformed-JSON case as a basic check; a BPP that returns 500 here
     fails admission.

The contract enforced by this module:

  Malformed JSON body  →  400 + ``{"message": {"ack": {"status": "NACK"}}, "error": {...}}``
"""
from __future__ import annotations

import pytest


@pytest.fixture
def malformed_json_body() -> str:
    # Truncated brace + bare identifier — guaranteed to fail json.loads
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
        # Error block exists and carries a stable, machine-readable code.
        assert "error" in body
        assert body["error"].get("code")

    async def test_malformed_init_also_nacks(self, client, malformed_json_body):
        resp = await client.post(
            "/api/webhook/init",
            content=malformed_json_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"]["ack"]["status"] == "NACK"

    async def test_malformed_unknown_action_also_nacks(self, client, malformed_json_body):
        # Unknown actions go through the same generic handler — they must
        # NACK consistently, not 500.
        resp = await client.post(
            "/api/webhook/something-unknown",
            content=malformed_json_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"]["ack"]["status"] == "NACK"

    async def test_empty_body_also_nacks(self, client):
        resp = await client.post(
            "/api/webhook/select",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["message"]["ack"]["status"] == "NACK"
