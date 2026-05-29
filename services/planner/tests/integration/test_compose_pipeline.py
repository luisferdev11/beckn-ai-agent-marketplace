"""Integration tests for POST /compose-pipeline.

The LLM is mocked at the engine layer. We test the endpoint's plumbing
around the validator: happy path, retry on validation failure, and
giving up after retry exhaustion.
"""
from __future__ import annotations

import pytest

from beckn_models.planning import (
    Plan,
    PlanEstimates,
    PlanStep,
    StepRecommendation,
)


def _good_plan(agent_id: str) -> Plan:
    return Plan(
        summary="Summarize the document",
        steps=[PlanStep(
            id="s1",
            skill_id="summarize",
            depends_on=[],
            recommended=StepRecommendation(
                agent_id=agent_id, name="X", provider="BPP-A",
                cost=0.05, currency="USD", latency_ms=3000, reason="best",
            ),
            alternatives=[],
            input_mapping={"text": "$pipeline_input.document"},
        )],
        estimates=PlanEstimates(total_cost=0.05, currency="USD", max_latency_ms=3000, steps_count=1),
    )


def _bad_plan_hallucinated_agent() -> Plan:
    return _good_plan(agent_id="ghost-agent-not-in-candidates")


@pytest.fixture
def mock_compose(monkeypatch):
    """Mock engine.compose_pipeline. Returns a queue of responses (per call)."""
    from app import engine

    queue: list[Plan | Exception] = []
    calls: list[str] = []

    async def _fake_compose(req, retry_hint: str = ""):
        calls.append(retry_hint)
        if not queue:
            raise RuntimeError("test bug: mock_compose called with empty queue")
        nxt = queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    monkeypatch.setattr(engine, "compose_pipeline", _fake_compose)
    return {"queue": queue, "calls": calls}


async def test_compose_pipeline_happy_path(client, mock_compose, summarize_candidate):
    mock_compose["queue"].append(_good_plan(summarize_candidate.agent_id))

    resp = await client.post("/compose-pipeline", json={
        "prompt": "Summarize this",
        "candidates": {"summarize": [summarize_candidate.model_dump()]},
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "Summarize the document"
    assert body["steps"][0]["recommended"]["agent_id"] == summarize_candidate.agent_id
    # No retry happened
    assert len(mock_compose["calls"]) == 1
    assert mock_compose["calls"][0] == ""


async def test_compose_pipeline_retries_on_validation_failure(client, mock_compose, summarize_candidate):
    """First LLM output is invalid (hallucinated agent), retry succeeds."""
    mock_compose["queue"].append(_bad_plan_hallucinated_agent())
    mock_compose["queue"].append(_good_plan(summarize_candidate.agent_id))

    resp = await client.post("/compose-pipeline", json={
        "prompt": "Summarize",
        "candidates": {"summarize": [summarize_candidate.model_dump()]},
    })

    assert resp.status_code == 200
    # Retry happened: 2 calls, second one had a retry_hint
    assert len(mock_compose["calls"]) == 2
    assert "RECOMMENDED_NOT_IN_CANDIDATES" in mock_compose["calls"][1]


async def test_compose_pipeline_returns_422_after_retry_exhaustion(client, mock_compose, summarize_candidate):
    """Both LLM attempts return invalid plans -> 422 with error list."""
    mock_compose["queue"].append(_bad_plan_hallucinated_agent())
    mock_compose["queue"].append(_bad_plan_hallucinated_agent())

    resp = await client.post("/compose-pipeline", json={
        "prompt": "Summarize",
        "candidates": {"summarize": [summarize_candidate.model_dump()]},
    })

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "INVALID_PLAN"
    codes = {e["code"] for e in detail["errors"]}
    assert "RECOMMENDED_NOT_IN_CANDIDATES" in codes


async def test_compose_pipeline_returns_503_on_llm_error(client, mock_compose, summarize_candidate):
    mock_compose["queue"].append(RuntimeError("Groq timeout"))

    resp = await client.post("/compose-pipeline", json={
        "prompt": "Summarize",
        "candidates": {"summarize": [summarize_candidate.model_dump()]},
    })

    assert resp.status_code == 503
    assert "PLANNER_LLM_ERROR" in resp.json()["detail"]
