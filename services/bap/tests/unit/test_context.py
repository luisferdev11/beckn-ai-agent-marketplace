"""
Unit tests for BAP context builder.

_build_context() produces the transport envelope for every Beckn request.
These tests ensure the fields are always well-formed before anything goes to ONIX.
"""

import re
import uuid
from app.routes.api import _build_context, _now_iso


class TestNowIso:
    def test_format_is_iso8601(self):
        ts = _now_iso()
        # Must match: 2026-04-22T05:36:08.055Z
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        assert re.match(pattern, ts), f"Unexpected timestamp format: {ts}"

    def test_ends_with_z(self):
        assert _now_iso().endswith("Z")

    def test_milliseconds_always_three_digits(self):
        for _ in range(20):
            ts = _now_iso()
            ms_part = ts.split(".")[1]
            assert len(ms_part) == 4, f"Expected 3 digits + Z, got: {ms_part}"  # '055Z'


class TestBuildContext:
    def test_required_fields_present(self):
        ctx = _build_context("select", "txn-123")
        required = ("networkId", "action", "version", "bapId", "bapUri",
                     "bppId", "bppUri", "transactionId", "messageId", "timestamp", "ttl")
        for field in required:
            assert field in ctx, f"Missing required field: {field}"

    def test_action_set_correctly(self):
        for action in ("select", "init", "confirm", "status", "cancel"):
            ctx = _build_context(action)
            assert ctx["action"] == action

    def test_provided_txn_id_is_reused(self):
        txn_id = str(uuid.uuid4())
        ctx = _build_context("select", txn_id)
        assert ctx["transactionId"] == txn_id

    def test_new_uuid_generated_when_no_txn_id(self):
        ctx = _build_context("select")
        # Should be a valid UUID
        parsed = uuid.UUID(ctx["transactionId"])
        assert str(parsed) == ctx["transactionId"]

    def test_message_id_is_always_new_uuid(self):
        ids = {_build_context("select", "same-txn")["messageId"] for _ in range(5)}
        assert len(ids) == 5, "messageId should be unique per call"

    def test_version_is_v2(self):
        assert _build_context("select")["version"] == "2.0.0"

    def test_ttl_is_iso8601_duration(self):
        ttl = _build_context("select")["ttl"]
        # PT30S is a valid ISO 8601 duration
        assert ttl.startswith("PT"), f"TTL should be ISO 8601 duration, got: {ttl}"

    def test_network_id_is_testnet(self):
        ctx = _build_context("select")
        assert "beckn" in ctx["networkId"].lower()
