"""Validator unit tests — exercises every check independently."""
from __future__ import annotations

import pytest

from app.validator import ValidationError, validate_plan
from beckn_models.planning import (
    AgentCandidate,
    Plan,
    PlanEstimates,
    PlanStep,
    StepAlternative,
    StepRecommendation,
)


def _step(
    sid: str,
    skill_id: str = "summarize",
    agent_id: str = "agent-summarizer-001",
    depends_on: list[str] | None = None,
    input_mapping: dict[str, str] | None = None,
    alternatives: list[StepAlternative] | None = None,
) -> PlanStep:
    return PlanStep(
        id=sid,
        skill_id=skill_id,
        depends_on=depends_on or [],
        recommended=StepRecommendation(
            agent_id=agent_id,
            name="X",
            provider="BPP-A",
            cost=0.05,
            currency="USD",
            latency_ms=3000,
            reason="picked",
        ),
        alternatives=alternatives or [],
        input_mapping=input_mapping or {},
    )


def _plan(steps: list[PlanStep], summary: str = "test") -> Plan:
    return Plan(
        summary=summary,
        steps=steps,
        estimates=PlanEstimates(
            total_cost=sum(s.recommended.cost for s in steps),
            currency="USD",
            max_latency_ms=max((s.recommended.latency_ms for s in steps), default=0),
            steps_count=len(steps),
        ),
    )


def _by_code(errors: list[ValidationError]) -> set[str]:
    return {e.code for e in errors}


def test_valid_single_step_plan_passes(summarize_candidate):
    plan = _plan([_step("s1", "summarize", summarize_candidate.agent_id)])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert errors == []


def test_valid_two_step_plan_passes(ocr_candidate, summarize_candidate):
    plan = _plan([
        _step("s1", "ocr", ocr_candidate.agent_id),
        _step(
            "s2",
            "summarize",
            summarize_candidate.agent_id,
            depends_on=["s1"],
            input_mapping={"text": "$steps.s1.extracted_text"},
        ),
    ])
    errors = validate_plan(plan, {
        "ocr": [ocr_candidate],
        "summarize": [summarize_candidate],
    })
    assert errors == []


def test_duplicate_step_id_is_detected(summarize_candidate):
    plan = _plan([
        _step("s1", "summarize", summarize_candidate.agent_id),
        _step("s1", "summarize", summarize_candidate.agent_id),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "DUPLICATE_STEP_ID" in _by_code(errors)


def test_unknown_depends_on_is_detected(summarize_candidate):
    plan = _plan([
        _step("s1", "summarize", summarize_candidate.agent_id, depends_on=["does-not-exist"]),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "UNKNOWN_DEPENDS_ON" in _by_code(errors)


def test_cycle_is_detected(summarize_candidate):
    # s1 -> s2 -> s1  (cycle)
    plan = _plan([
        _step("s1", "summarize", summarize_candidate.agent_id, depends_on=["s2"]),
        _step("s2", "summarize", summarize_candidate.agent_id, depends_on=["s1"]),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "CYCLE_DETECTED" in _by_code(errors)


def test_recommended_not_in_candidates(summarize_candidate):
    plan = _plan([_step("s1", "summarize", agent_id="hallucinated-agent")])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "RECOMMENDED_NOT_IN_CANDIDATES" in _by_code(errors)


def test_no_candidates_for_skill(summarize_candidate):
    plan = _plan([_step("s1", "ocr", summarize_candidate.agent_id)])
    # candidates only has "summarize", but the step asks for "ocr"
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "NO_CANDIDATES_FOR_SKILL" in _by_code(errors)


def test_alternative_not_in_candidates(summarize_candidate, summarize_alt_candidate):
    plan = _plan([
        _step(
            "s1",
            "summarize",
            summarize_candidate.agent_id,
            alternatives=[StepAlternative(
                agent_id="ghost-agent",
                name="Ghost",
                cost=0.01,
                latency_ms=1000,
                note="not real",
            )],
        ),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate, summarize_alt_candidate]})
    assert "ALTERNATIVE_NOT_IN_CANDIDATES" in _by_code(errors)


def test_mapping_references_unknown_step(summarize_candidate):
    plan = _plan([
        _step(
            "s1",
            "summarize",
            summarize_candidate.agent_id,
            depends_on=[],
            input_mapping={"text": "$steps.ghost.extracted_text"},
        ),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "UNKNOWN_MAPPING_STEP" in _by_code(errors)


def test_mapping_without_dependency(ocr_candidate, summarize_candidate):
    # Maps from s1 but doesn't declare it in depends_on
    plan = _plan([
        _step("s1", "ocr", ocr_candidate.agent_id),
        _step(
            "s2",
            "summarize",
            summarize_candidate.agent_id,
            depends_on=[],  # missing s1
            input_mapping={"text": "$steps.s1.extracted_text"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [ocr_candidate], "summarize": [summarize_candidate]})
    assert "MAPPING_WITHOUT_DEPENDENCY" in _by_code(errors)


def test_unknown_output_field(ocr_candidate, summarize_candidate):
    # ocr has output fields extracted_text + page_count. Reference 'foo' → fail.
    plan = _plan([
        _step("s1", "ocr", ocr_candidate.agent_id),
        _step(
            "s2",
            "summarize",
            summarize_candidate.agent_id,
            depends_on=["s1"],
            input_mapping={"text": "$steps.s1.foo"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [ocr_candidate], "summarize": [summarize_candidate]})
    assert "UNKNOWN_OUTPUT_FIELD" in _by_code(errors)


def test_pipeline_input_mapping_is_not_validated(summarize_candidate):
    plan = _plan([
        _step(
            "s1",
            "summarize",
            summarize_candidate.agent_id,
            input_mapping={"text": "$pipeline_input.document", "lang": "es"},
        ),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    # $pipeline_input.<field> and literals are accepted unconditionally
    assert errors == []


def test_malformed_mapping_source(summarize_candidate):
    plan = _plan([
        _step(
            "s1",
            "summarize",
            summarize_candidate.agent_id,
            input_mapping={"text": "$steps."},
        ),
    ])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "MALFORMED_MAPPING" in _by_code(errors)


def test_diamond_dag_is_valid(ocr_candidate, summarize_candidate):
    """s1, s2 parallel → s3 depends on both. Valid DAG."""
    plan = _plan([
        _step("s1", "ocr", ocr_candidate.agent_id),
        _step("s2", "ocr", ocr_candidate.agent_id),
        _step(
            "s3",
            "summarize",
            summarize_candidate.agent_id,
            depends_on=["s1", "s2"],
            input_mapping={"text": "$steps.s1.extracted_text"},
        ),
    ])
    errors = validate_plan(plan, {
        "ocr": [ocr_candidate],
        "summarize": [summarize_candidate],
    })
    assert errors == []


# ── Required-input and type-compatibility checks ────────────


def _candidate(agent_id: str, skill: str, input_schema: dict | None = None, output_schema: dict | None = None):
    from beckn_models.planning import AgentCandidate
    return AgentCandidate(
        agent_id=agent_id, name=agent_id, provider="P",
        skill_ids=[skill],
        input_schema=input_schema,
        output_schema=output_schema,
    )


def test_required_input_must_be_mapped(summarize_candidate):
    # summarize_candidate requires 'text'. Map nothing -> fail.
    plan = _plan([_step("s1", "summarize", summarize_candidate.agent_id, input_mapping={})])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert "REQUIRED_INPUT_NOT_MAPPED" in _by_code(errors)


def test_optional_input_can_be_missing(summarize_candidate):
    # summarize_candidate has optional 'lang'. Mapping only 'text' is fine.
    plan = _plan([_step(
        "s1", "summarize", summarize_candidate.agent_id,
        input_mapping={"text": "$pipeline_input.document"},
    )])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert errors == []


def test_type_mismatch_integer_to_string():
    """Source field is integer; target field is string -> TYPE_MISMATCH."""
    producer = _candidate(
        "producer", "ocr",
        output_schema={"type": "object", "properties": {
            "page_count": {"type": "integer"},
        }},
    )
    consumer = _candidate(
        "consumer", "summarize",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    plan = _plan([
        _step("s1", "ocr", producer.agent_id, input_mapping={}),
        _step(
            "s2", "summarize", consumer.agent_id,
            depends_on=["s1"],
            input_mapping={"text": "$steps.s1.page_count"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [producer], "summarize": [consumer]})
    assert "TYPE_MISMATCH" in _by_code(errors)


def test_type_match_string_to_string():
    """Compatible: string -> string."""
    producer = _candidate(
        "producer", "ocr",
        output_schema={"type": "object", "properties": {"extracted_text": {"type": "string"}}},
    )
    consumer = _candidate(
        "consumer", "summarize",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    plan = _plan([
        _step("s1", "ocr", producer.agent_id, input_mapping={}),
        _step(
            "s2", "summarize", consumer.agent_id,
            depends_on=["s1"],
            input_mapping={"text": "$steps.s1.extracted_text"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [producer], "summarize": [consumer]})
    assert errors == []


def test_integer_is_compatible_with_number():
    """integer is a subtype of number per JSON Schema."""
    producer = _candidate(
        "producer", "ocr",
        output_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
    )
    consumer = _candidate(
        "consumer", "summarize",
        input_schema={"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]},
    )
    plan = _plan([
        _step("s1", "ocr", producer.agent_id, input_mapping={}),
        _step(
            "s2", "summarize", consumer.agent_id,
            depends_on=["s1"],
            input_mapping={"amount": "$steps.s1.count"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [producer], "summarize": [consumer]})
    assert errors == []


def test_literal_string_into_integer_field_fails():
    """Literal '5' is type string, not integer. Target wants integer -> fail."""
    consumer = _candidate(
        "consumer", "summarize",
        input_schema={
            "type": "object",
            "properties": {"page_count": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["text", "page_count"],
        },
    )
    plan = _plan([_step(
        "s1", "summarize", consumer.agent_id,
        input_mapping={"text": "$pipeline_input.document", "page_count": "5"},
    )])
    errors = validate_plan(plan, {"summarize": [consumer]})
    assert "LITERAL_TYPE_MISMATCH" in _by_code(errors)


def test_literal_string_into_string_field_passes(summarize_candidate):
    """Literal 'es' is a string, target accepts string -> ok."""
    plan = _plan([_step(
        "s1", "summarize", summarize_candidate.agent_id,
        input_mapping={"text": "$pipeline_input.document", "lang": "es"},
    )])
    errors = validate_plan(plan, {"summarize": [summarize_candidate]})
    assert errors == []


def test_nullable_target_accepts_non_null_source():
    """Target accepts ["string", "null"] -> any string source is fine."""
    producer = _candidate(
        "p", "ocr",
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    consumer = _candidate(
        "c", "summarize",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": ["string", "null"]}},
            "required": ["text"],
        },
    )
    plan = _plan([
        _step("s1", "ocr", producer.agent_id, input_mapping={}),
        _step(
            "s2", "summarize", consumer.agent_id,
            depends_on=["s1"],
            input_mapping={"text": "$steps.s1.text"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [producer], "summarize": [consumer]})
    assert errors == []


def test_missing_target_schema_is_permissive():
    """No input_schema on the target → no type errors raised."""
    producer = _candidate(
        "p", "ocr",
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    consumer = _candidate("c", "summarize", input_schema=None)
    plan = _plan([
        _step("s1", "ocr", producer.agent_id, input_mapping={}),
        _step(
            "s2", "summarize", consumer.agent_id,
            depends_on=["s1"],
            input_mapping={"anything": "$steps.s1.text"},
        ),
    ])
    errors = validate_plan(plan, {"ocr": [producer], "summarize": [consumer]})
    # No type / required errors when target has no schema
    codes = _by_code(errors)
    assert "TYPE_MISMATCH" not in codes
    assert "REQUIRED_INPUT_NOT_MAPPED" not in codes
