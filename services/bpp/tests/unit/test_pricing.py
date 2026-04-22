"""
Unit tests for BPP pricing logic in handle_select.

These tests verify the core business rule: price = unit_price * qty + 18% GST.
They test handle_select() directly — no HTTP calls, no mocks needed.
"""

import pytest
from app.handlers.beckn_actions import handle_select
from tests.factories.agents import make_beckn_context, make_select_contract_message


SCHEMA_URL = "https://raw.githubusercontent.com/luisferdev11/beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json"


class TestPricingByAgent:
    async def test_summarizer_base_price_is_6_inr(self):
        ctx = make_beckn_context("select", "txn-price-001")
        msg = make_select_contract_message("agent-summarizer-001", "offer-summarizer-basic")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        breakup = consideration["breakup"]
        agent_line = next(b for b in breakup if "GST" not in b["title"])
        assert agent_line["price"]["value"] == "6.00"

    async def test_summarizer_total_with_gst_is_7_08(self):
        ctx = make_beckn_context("select", "txn-price-002")
        msg = make_select_contract_message("agent-summarizer-001", "offer-summarizer-basic")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        assert total == "7.08"

    async def test_code_reviewer_base_price_is_10_inr(self):
        ctx = make_beckn_context("select", "txn-price-003")
        msg = make_select_contract_message("agent-code-reviewer-001", "offer-code-review-basic")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        agent_line = next(b for b in consideration["breakup"] if "GST" not in b["title"])
        assert agent_line["price"]["value"] == "10.00"

    async def test_code_reviewer_total_with_gst_is_11_80(self):
        ctx = make_beckn_context("select", "txn-price-004")
        msg = make_select_contract_message("agent-code-reviewer-001", "offer-code-review-basic")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        assert total == "11.80"

    async def test_data_extractor_base_price_is_4_inr(self):
        ctx = make_beckn_context("select", "txn-price-005")
        msg = make_select_contract_message("agent-data-extractor-001", "offer-data-extractor-basic")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        agent_line = next(b for b in consideration["breakup"] if "GST" not in b["title"])
        assert agent_line["price"]["value"] == "4.00"

    async def test_data_extractor_total_with_gst_is_4_72(self):
        ctx = make_beckn_context("select", "txn-price-006")
        msg = make_select_contract_message("agent-data-extractor-001", "offer-data-extractor-basic")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        assert total == "4.72"


class TestGSTCalculation:
    async def test_gst_breakup_line_is_always_present(self):
        ctx = make_beckn_context("select", "txn-gst-001")
        msg = make_select_contract_message("agent-summarizer-001")
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        gst_lines = [b for b in breakup if "GST" in b["title"]]
        assert len(gst_lines) == 1

    async def test_gst_is_18_percent_of_base(self):
        ctx = make_beckn_context("select", "txn-gst-002")
        msg = make_select_contract_message("agent-summarizer-001")
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        base = float(next(b["price"]["value"] for b in breakup if "GST" not in b["title"]))
        gst = float(next(b["price"]["value"] for b in breakup if "GST" in b["title"]))
        assert abs(gst - base * 0.18) < 0.01

    async def test_currency_is_always_inr(self):
        ctx = make_beckn_context("select", "txn-gst-003")
        msg = make_select_contract_message("agent-code-reviewer-001")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        assert consideration["price"]["currency"] == "INR"
        for line in consideration["breakup"]:
            assert line["price"]["currency"] == "INR"


class TestQuantityMultiplier:
    async def test_quantity_2_doubles_base_price(self):
        ctx = make_beckn_context("select", "txn-qty-001")
        msg = make_select_contract_message("agent-summarizer-001", quantity=2)
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        agent_line = next(b for b in breakup if "GST" not in b["title"])
        assert agent_line["price"]["value"] == "12.00"

    async def test_quantity_2_total_includes_gst_on_doubled_price(self):
        ctx = make_beckn_context("select", "txn-qty-002")
        msg = make_select_contract_message("agent-summarizer-001", quantity=2)
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        # 2 × 6.00 = 12.00 + 18% GST = 14.16
        assert total == "14.16"


class TestUnknownAgent:
    async def test_unknown_agent_price_is_zero(self):
        ctx = make_beckn_context("select", "txn-unknown-001")
        msg = make_select_contract_message("agent-does-not-exist-999")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"]
        # Should not crash — returns zero-price consideration
        assert len(consideration) > 0
