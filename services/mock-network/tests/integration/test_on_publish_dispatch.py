"""Tests for the on_publish callback delivery path.

The catalog service must POST a Beckn-shaped on_publish envelope to the
BPP backend's webhook (``<backend_health_url>/api/webhook/on_publish``).
We mock the HTTP layer with respx so the test never opens a socket.

The bpp-provider subscriber seeded by the conftest declares
``backend_health_url = http://bpp-provider:3002``, so that is the URL we
expect to see in respx.
"""
from __future__ import annotations

import respx

from app.catalog import service as catalog_service


@respx.mock
async def test_dispatch_on_publish_posts_to_backend_webhook(fake_subscribers):
    target = "http://bpp-provider:3002/api/webhook/on_publish"
    route = respx.post(target).respond(200, json={"message": {"ack": {"status": "ACK"}}})

    envelope = {
        "context": {
            "action": "catalog/publish",
            "bppId": "bpp.example.com",
            "transactionId": "txn-1",
            "messageId": "msg-1",
        },
        "message": {"catalogs": []},
    }
    results = [{"catalogId": "c1", "status": "ACCEPTED",
                "stats": {"itemCount": 1, "itemCountAccepted": 1, "itemCountRejected": 0},
                "errors": []}]

    await catalog_service.dispatch_on_publish(envelope, results)

    assert route.called, "on_publish was not POSTed to the BPP backend"
    body = route.calls.last.request.read().decode()
    assert "catalog/on_publish" in body
    assert "ACCEPTED" in body


@respx.mock
async def test_dispatch_silent_when_subscriber_unknown(fake_subscribers):
    """Unknown bppId must not raise — we just log and move on so a buggy
    BPP cannot crash the CDS background task."""
    envelope = {
        "context": {"bppId": "ghost.example.com", "transactionId": "txn-1", "messageId": "msg-1"},
        "message": {"catalogs": []},
    }
    # Should complete without raising; no respx mock needed because no
    # HTTP call is expected.
    await catalog_service.dispatch_on_publish(envelope, results=[])


@respx.mock
async def test_dispatch_silent_when_backend_url_missing(fake_subscribers):
    """If a subscriber lacks backend_health_url, we cannot route the
    callback — skip gracefully rather than crashing."""
    fake_subscribers["bpp.example.com"]["backend_health_url"] = None
    envelope = {
        "context": {"bppId": "bpp.example.com", "transactionId": "txn-1", "messageId": "msg-1"},
        "message": {"catalogs": []},
    }
    await catalog_service.dispatch_on_publish(envelope, results=[])
