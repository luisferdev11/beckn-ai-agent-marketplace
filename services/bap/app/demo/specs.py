"""Frozen contract for the Story 1 cross-BPP demo.

Everything that is "controlled" about the demo lives here: the two
agents we expect, their BPPs, the declared JSON Schemas, the planner
prompt and the canonical plan shape. The orchestrator (``runner.py``)
calls the real planner and the real Beckn flow; this module exists so
the runner can fall back deterministically if the planner produces an
incompatible plan — without that fallback the demo would be at the
mercy of an LLM on every run.

When the dynamic pipeline (planner + dynamic agent discovery) is hardened
in a future iteration, this file becomes the integration test fixture
and the runner stops needing the fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# The user-visible prompt the demo runs. We also send it to the planner
# verbatim so the operator's logs show what the LLM was asked.
DEMO_PROMPT = (
    "Summarize this Indian banking / regulatory document and extract the "
    "key entities (organizations, dates, regulatory references, monetary "
    "amounts, obligations) from the summary."
)


# A representative RBI-style sample so the frontend can pre-fill the
# textarea. Kept short on purpose — under the agents' input budgets.
SAMPLE_DOCUMENT = """\
RBI Master Circular No. DBR.No.BP.BC.13/21.06.001/2025-26
Effective Date: 1 July 2025

Subject: Prudential Norms on Capital Adequacy — Basel III Framework

To: All Scheduled Commercial Banks (excluding Regional Rural Banks)
Issued by: Reserve Bank of India, Department of Banking Regulation

1. Applicability
   This Master Circular consolidates instructions issued to banks on
   capital adequacy. It supersedes the circular dated 1 April 2024.

2. Minimum Capital Requirements
   2.1 Common Equity Tier 1 (CET1) capital ratio: 5.5%
   2.2 Tier 1 capital ratio: 7.0%
   2.3 Total Capital Ratio: 9.0%
   2.4 Capital Conservation Buffer: an additional 2.5% of CET1.

3. Reporting Obligations
   Banks shall submit quarterly returns to the Department of Banking
   Supervision in Form C within 30 days of the close of each quarter.
   The first return under this circular is due 30 October 2025.

4. Penal Provisions
   Failure to maintain the minimum capital ratios shall attract a
   penalty of ₹1,00,000 per day per breach under Section 47A of the
   Banking Regulation Act, 1949.

5. Implementation
   Banks must implement the revised framework by 31 December 2025 and
   confirm compliance to the Reserve Bank of India through their
   Statutory Auditors.
"""


# ── Pipeline contract ──────────────────────────────────────────────


@dataclass(frozen=True)
class StepSpec:
    """One step of the canonical pipeline.

    ``input_schema`` and ``output_schema`` are real JSON Schema
    (draft-2020-12). The orchestrator validates the inbound payload
    against ``input_schema`` BEFORE sending the select, and the
    on_status result against ``output_schema`` AFTER it arrives — so
    misbehaving agents are caught at the marketplace boundary, not
    deep inside a downstream consumer.
    """
    step_id: str
    skill_id: str
    agent_id: str
    bpp_id: str
    bpp_uri: str
    offer_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


# Step 1 — Tecla legal summarizer (India, English/Hindi). Schemas mirror
# the AgentFacts published in infra/db/bpp/migrations/002_seed_data.sql.
STEP_SUMMARIZE = StepSpec(
    step_id="s1",
    skill_id="document_summarization",
    agent_id="agent-summarizer-001",
    bpp_id="bpp.example.com",
    bpp_uri="http://onix-bpp:8082/bpp/receiver",
    offer_id="offer-summarizer-basic",
    description="Summarize a regulatory document into prose + 3-7 key points.",
    input_schema={
        "type": "object",
        "properties": {
            "document": {"type": "string", "minLength": 1},
            "language": {"type": "string"},
        },
        "required": ["document"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "language": {"type": "string"},
        },
        "required": ["summary", "key_points"],
    },
)

# Step 2 — Serg structured extractor (Mexico). Schemas mirror the
# ``inputSchemaContract`` and ``outputSchemaContract`` advertised on
# the Serg in-memory catalog (services/bpp-serg/app/catalog_data.py).
STEP_EXTRACT = StepSpec(
    step_id="s2",
    skill_id="entity_extraction",
    agent_id="extractor-v1",
    bpp_id="bpp-serg.example.com",
    bpp_uri="http://onix-bpp-serg:8083/bpp/receiver",
    offer_id="offer-extractor-v1",
    description="Extract organizations, dates, references, amounts, obligations.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
        },
        "required": ["text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "organizations":         {"type": "array", "items": {"type": "string"}},
            "dates":                 {"type": "array", "items": {"type": "string"}},
            "regulatory_references": {"type": "array", "items": {"type": "string"}},
            "monetary_amounts":      {"type": "array", "items": {"type": "string"}},
            "obligations":           {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "organizations", "dates", "regulatory_references",
            "monetary_amounts", "obligations",
        ],
    },
)


PIPELINE: list[StepSpec] = [STEP_SUMMARIZE, STEP_EXTRACT]


# The mapping the runner uses to bridge step1.output → step2.input.
# Keeping it explicit (rather than letting an LLM decide) is what
# makes this iteration "controlled". The shape mirrors the planner's
# ``input_mapping`` ({"target_field": "$steps.<step>.<source_field>"}).
STEP2_INPUT_MAPPING: dict[str, str] = {
    "text": "$steps.s1.summary",
}


def expected_planner_skills() -> list[str]:
    """Skills we expect the planner to extract from DEMO_PROMPT."""
    return [STEP_SUMMARIZE.skill_id, STEP_EXTRACT.skill_id]
