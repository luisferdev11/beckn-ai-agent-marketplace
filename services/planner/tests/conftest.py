"""Shared fixtures for planner tests."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from beckn_models.planning import AgentCandidate


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def ocr_candidate() -> AgentCandidate:
    """A representative OCR agent. Output_schema declares `extracted_text` + `page_count`."""
    return AgentCandidate(
        agent_id="agent-ocr-001",
        name="OCR Pro",
        provider="BPP-A",
        skill_ids=["ocr"],
        input_modes=["application/pdf", "image/jpeg"],
        output_modes=["application/json"],
        supported_languages=["en", "es"],
        input_schema={
            "type": "object",
            "properties": {"document": {"type": "string"}},
            "required": ["document"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "extracted_text": {"type": "string"},
                "page_count": {"type": "integer"},
            },
        },
        pricing_value=0.05,
        pricing_currency="USD",
        max_latency_ms=5000,
        accuracy=0.95,
        jurisdiction="IN",
    )


@pytest.fixture
def summarize_candidate() -> AgentCandidate:
    """A multilingual summarizer. Accepts `text` and `lang`, outputs `summary`."""
    return AgentCandidate(
        agent_id="agent-summarizer-001",
        name="Multilingual Summarizer",
        provider="BPP-C",
        skill_ids=["summarize"],
        input_modes=["text/plain"],
        output_modes=["application/json"],
        supported_languages=["en", "es", "fr"],
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "lang": {"type": "string"},
            },
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
        pricing_value=0.08,
        pricing_currency="USD",
        max_latency_ms=3000,
        accuracy=0.92,
        jurisdiction="IN",
    )


@pytest.fixture
def summarize_alt_candidate() -> AgentCandidate:
    """A cheaper English-only summarizer (alternative for the summarize step)."""
    return AgentCandidate(
        agent_id="agent-summarizer-002",
        name="Cheap English Summary",
        provider="BPP-A",
        skill_ids=["summarize"],
        input_modes=["text/plain"],
        output_modes=["application/json"],
        supported_languages=["en"],
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        pricing_value=0.02,
        pricing_currency="USD",
        max_latency_ms=2500,
        accuracy=0.88,
    )
