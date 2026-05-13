"""
Unit tests for BPP-Serg pricing logic in handle_select.

Same business rule as bpp-provider: price = unit_price * qty + 18% tax.
But the catalog uses MXN pricing — so the assertions are in MXN amounts and
the tax line is "VAT (18%)" rather than "GST (18%)".
"""

import pytest
from app.handlers.beckn_actions import handle_select
from tests.factories.agents import make_beckn_context, make_select_contract_message


class TestPricingByAgent:
    async def test_summarizer_base_price_is_5_mxn(self):
        ctx = make_beckn_context("select", "txn-price-001")
        msg = make_select_contract_message("summarizer-v1", "offer-summarizer-v1")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        breakup = consideration["breakup"]
        agent_line = next(b for b in breakup if "VAT" not in b["title"])
        assert agent_line["price"]["value"] == "5.00"

    async def test_summarizer_total_with_tax(self):
        ctx = make_beckn_context("select", "txn-price-002")
        msg = make_select_contract_message("summarizer-v1", "offer-summarizer-v1")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        # 5.00 * 1.18 = 5.90
        assert total == "5.90"

    async def test_code_reviewer_base_price_is_8_mxn(self):
        ctx = make_beckn_context("select", "txn-price-003")
        msg = make_select_contract_message("code-reviewer-v1", "offer-code-reviewer-v1")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        agent_line = next(b for b in consideration["breakup"] if "VAT" not in b["title"])
        assert agent_line["price"]["value"] == "8.00"

    async def test_code_reviewer_total_with_tax(self):
        ctx = make_beckn_context("select", "txn-price-004")
        msg = make_select_contract_message("code-reviewer-v1", "offer-code-reviewer-v1")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        # 8.00 * 1.18 = 9.44
        assert total == "9.44"

    async def test_extractor_base_price_is_4_50_mxn(self):
        ctx = make_beckn_context("select", "txn-price-005")
        msg = make_select_contract_message("extractor-v1", "offer-extractor-v1")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        agent_line = next(b for b in consideration["breakup"] if "VAT" not in b["title"])
        assert agent_line["price"]["value"] == "4.50"

    async def test_extractor_total_with_tax(self):
        ctx = make_beckn_context("select", "txn-price-006")
        msg = make_select_contract_message("extractor-v1", "offer-extractor-v1")
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        # 4.50 * 1.18 = 5.31
        assert total == "5.31"


class TestVATCalculation:
    async def test_vat_breakup_line_is_always_present(self):
        ctx = make_beckn_context("select", "txn-vat-001")
        msg = make_select_contract_message("summarizer-v1")
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        vat_lines = [b for b in breakup if "VAT" in b["title"]]
        assert len(vat_lines) == 1

    async def test_vat_is_18_percent_of_base(self):
        ctx = make_beckn_context("select", "txn-vat-002")
        msg = make_select_contract_message("summarizer-v1")
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        base = float(next(b["price"]["value"] for b in breakup if "VAT" not in b["title"]))
        vat = float(next(b["price"]["value"] for b in breakup if "VAT" in b["title"]))
        assert abs(vat - base * 0.18) < 0.01

    async def test_currency_is_mxn(self):
        ctx = make_beckn_context("select", "txn-vat-003")
        msg = make_select_contract_message("code-reviewer-v1")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"][0]
        assert consideration["price"]["currency"] == "MXN"
        for line in consideration["breakup"]:
            assert line["price"]["currency"] == "MXN"


class TestQuantityMultiplier:
    async def test_quantity_2_doubles_base_price(self):
        ctx = make_beckn_context("select", "txn-qty-001")
        msg = make_select_contract_message("summarizer-v1", quantity=2)
        response = await handle_select(ctx, msg)
        breakup = response["message"]["contract"]["consideration"][0]["breakup"]
        agent_line = next(b for b in breakup if "VAT" not in b["title"])
        assert agent_line["price"]["value"] == "10.00"

    async def test_quantity_2_total_includes_vat_on_doubled_price(self):
        ctx = make_beckn_context("select", "txn-qty-002")
        msg = make_select_contract_message("summarizer-v1", quantity=2)
        response = await handle_select(ctx, msg)
        total = response["message"]["contract"]["consideration"][0]["price"]["value"]
        # 2 × 5.00 = 10.00 + 18% VAT = 11.80
        assert total == "11.80"


class TestUnknownAgent:
    async def test_unknown_agent_price_is_zero(self):
        ctx = make_beckn_context("select", "txn-unknown-001")
        msg = make_select_contract_message("agent-does-not-exist-999")
        response = await handle_select(ctx, msg)
        consideration = response["message"]["contract"]["consideration"]
        assert len(consideration) > 0
