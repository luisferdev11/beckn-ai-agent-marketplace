"""Integration tests for POST /extract-skills.

The LLM call is mocked at the engine layer (no Groq dependency).
"""
from __future__ import annotations

import pytest

from beckn_models.planning import ExtractSkillsResponse, SkillRequest


@pytest.fixture
def mock_extract(monkeypatch):
    """Replace engine.extract_skills with a controllable async stub."""
    from app import engine

    calls: list[dict] = []
    response_holder: list[ExtractSkillsResponse] = []
    error_holder: list[Exception] = []

    async def _fake_extract(req):
        calls.append({"prompt": req.prompt})
        if error_holder:
            raise error_holder[0]
        return response_holder[0]

    monkeypatch.setattr(engine, "extract_skills", _fake_extract)

    return {"calls": calls, "set_response": response_holder.append, "set_error": error_holder.append}


async def test_extract_skills_happy_path(client, mock_extract):
    mock_extract["set_response"](ExtractSkillsResponse(
        skills_needed=[SkillRequest(
            skill_id="summarize",
            description="summarize a document into Spanish preserving key points",
            filters={"language": "es"},
            reason="user asked in Spanish",
        )],
        summary="Summarize in Spanish",
    ))

    resp = await client.post("/extract-skills", json={
        "prompt": "Resume esto en español",
        "input_format": "text/plain",
        "output_format": "text/plain",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "Summarize in Spanish"
    assert body["skills_needed"][0]["skill_id"] == "summarize"
    assert body["skills_needed"][0]["description"] == (
        "summarize a document into Spanish preserving key points"
    )
    assert body["skills_needed"][0]["filters"] == {"language": "es"}
    assert len(mock_extract["calls"]) == 1


async def test_extract_skills_returns_422_on_empty_plan(client, mock_extract):
    """Empty skills_needed is the only ValueError path left after dropping the registry constraint."""
    mock_extract["set_error"](ValueError("LLM returned no skills — cannot proceed with empty plan"))

    resp = await client.post("/extract-skills", json={
        "prompt": "garbled nonsense input",
        "input_format": "text/plain",
        "output_format": "text/plain",
    })

    assert resp.status_code == 422
    assert "no skills" in resp.json()["detail"]


async def test_extract_skills_returns_503_on_unexpected_error(client, mock_extract):
    mock_extract["set_error"](RuntimeError("Groq network blip"))

    resp = await client.post("/extract-skills", json={
        "prompt": "anything",
        "input_format": "text/plain",
        "output_format": "text/plain",
    })

    assert resp.status_code == 503
    assert "PLANNER_LLM_ERROR" in resp.json()["detail"]
