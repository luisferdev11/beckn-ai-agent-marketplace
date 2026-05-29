"""Models — quick sanity checks that Pydantic shapes round-trip cleanly."""
from __future__ import annotations

from beckn_models.planning import (
    AgentCandidate,
    ComposeRequest,
    ExtractSkillsRequest,
    ExtractSkillsResponse,
    Plan,
    PlanEstimates,
    PlanRequest,
    PlanResponse,
    PlanStep,
    SkillRequest,
    StepAlternative,
    StepRecommendation,
)


def test_extract_skills_response_round_trip():
    payload = {
        "skills_needed": [
            {
                "skill_id": "ocr",
                "description": "extract text from a scanned PDF document",
                "filters": {"modality": "pdf"},
                "reason": "input is PDF",
            },
        ],
        "summary": "Extract text",
    }
    resp = ExtractSkillsResponse.model_validate(payload)
    assert resp.summary == "Extract text"
    assert resp.skills_needed[0].skill_id == "ocr"
    assert resp.skills_needed[0].description == "extract text from a scanned PDF document"
    assert resp.model_dump()["skills_needed"][0]["filters"] == {"modality": "pdf"}


def test_plan_response_with_null_plan():
    """When no candidates are found, we return plan=null + error string."""
    resp = PlanResponse(plan=None, error="No candidates for skill 'ocr'", transaction_ids=["abc"])
    dumped = resp.model_dump()
    assert dumped["plan"] is None
    assert dumped["error"]
    assert dumped["transaction_ids"] == ["abc"]


def test_full_plan_round_trip():
    plan = Plan(
        summary="OCR then summarize",
        steps=[
            PlanStep(
                id="s1",
                skill_id="ocr",
                depends_on=[],
                recommended=StepRecommendation(
                    agent_id="a1", name="OCR Pro", provider="BPP-A",
                    cost=0.05, currency="USD", latency_ms=5000, reason="best",
                ),
                alternatives=[],
                input_mapping={"document": "$pipeline_input.document"},
            ),
            PlanStep(
                id="s2",
                skill_id="summarize",
                depends_on=["s1"],
                recommended=StepRecommendation(
                    agent_id="a2", name="Sum", provider="BPP-C",
                    cost=0.08, currency="USD", latency_ms=3000, reason="es support",
                ),
                alternatives=[
                    StepAlternative(agent_id="a3", name="Alt", cost=0.02, latency_ms=2500, note="cheaper")
                ],
                input_mapping={"text": "$steps.s1.extracted_text", "lang": "es"},
            ),
        ],
        estimates=PlanEstimates(total_cost=0.13, currency="USD", max_latency_ms=8000, steps_count=2),
    )
    # Round-trip through dict
    Plan.model_validate(plan.model_dump())


def test_agent_candidate_defaults():
    c = AgentCandidate(agent_id="x", name="X", provider="P")
    assert c.skill_ids == []
    assert c.pricing_value == 0.0
    assert c.pricing_currency == "USD"
    assert c.accuracy is None
    assert c.input_schema is None
