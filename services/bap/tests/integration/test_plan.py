"""
Integration tests for POST /api/plan — BAP-side orchestration.

The planner service is mocked via respx; ONIX is mocked via the existing
`mock_onix` fixture; on_discover callbacks are injected directly into the
fake_db so the polling loop returns immediately.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx as respx_lib
from httpx import Response

from app.config import PLANNER_URL


PLANNER_EXTRACT_URL = f"{PLANNER_URL}/extract-skills"
PLANNER_COMPOSE_URL = f"{PLANNER_URL}/compose-pipeline"


# ── Fixture builders ─────────────────────────────────────────

def _on_discover_callback(txn_id: str, agent_id: str, skill_id: str = "summarize") -> dict:
    """Build a fake on_discover callback as it would land in fake_db.callbacks."""
    return {
        "transaction_id": txn_id,
        "action": "on_discover",
        "context": {"action": "on_discover", "transactionId": txn_id},
        "message": {
            "catalogs": [{
                "id": "cat-1",
                "resources": [{
                    "id": agent_id,
                    "descriptor": {"name": "Test Agent"},
                    "resourceAttributes": {
                        "label": "Test Agent",
                        "skills": [{
                            "id": skill_id,
                            "description": "Test",
                            "inputModes": ["text/plain"],
                            "outputModes": ["application/json"],
                            "supportedLanguages": ["en", "es"],
                        }],
                        "pricing": {"value": 0.05, "currency": "USD", "model": "per_task"},
                        "sla": {"maxLatencyMs": 3000, "accuracy": 0.92},
                        "provider": {"name": "Test Provider"},
                        "jurisdiction": "IN",
                        "outputSchema": {
                            "type": "object",
                            "properties": {"summary": {"type": "string"}},
                        },
                    },
                }],
                "offers": [{"id": "offer-1", "resourceIds": [agent_id]}],
            }],
        },
        "error": None,
    }


def _good_plan_response(agent_id: str) -> dict:
    return {
        "summary": "Summarize the document",
        "steps": [{
            "id": "s1",
            "skill_id": "summarize",
            "depends_on": [],
            "recommended": {
                "agent_id": agent_id,
                "name": "Test Agent",
                "provider": "Test Provider",
                "cost": 0.05,
                "currency": "USD",
                "latency_ms": 3000,
                "reason": "best fit",
            },
            "alternatives": [],
            "input_mapping": {"text": "$pipeline_input.document"},
        }],
        "estimates": {
            "total_cost": 0.05,
            "currency": "USD",
            "max_latency_ms": 3000,
            "steps_count": 1,
        },
        "on_error": "fail_fast",
    }


def _extract_response(skill_id: str = "summarize") -> dict:
    return {
        "skills_needed": [{
            "skill_id": skill_id,
            "description": f"summarize a legal document in Spanish ({skill_id})",
            "filters": {"language": "es"},
            "reason": "user wants Spanish summary",
        }],
        "summary": "Summarize in Spanish",
    }


async def _seed_callback_loop(fake_db: dict, mock_onix, agent_id: str):
    """
    Background task: every 50ms, scan the captured ONIX discover calls and
    inject a matching on_discover callback for any txn_id we haven't seen yet.

    This emulates the asynchronous Beckn callback path without standing up
    real ONIX or BPP services.
    """
    seen: set[str] = set()
    while True:
        for call in mock_onix["discover"].calls:
            try:
                body = json.loads(call.request.content)
            except Exception:
                continue
            txn_id = body["context"]["transactionId"]
            if txn_id in seen:
                continue
            seen.add(txn_id)
            fake_db["callbacks"].append(_on_discover_callback(txn_id, agent_id))
        await asyncio.sleep(0.05)


# ── Tests ────────────────────────────────────────────────────

async def test_plan_happy_path(client, fake_db, mock_onix):
    agent_id = "agent-summarizer-test"
    with respx_lib.mock(assert_all_called=False) as router:
        router.post(PLANNER_EXTRACT_URL).mock(return_value=Response(200, json=_extract_response()))
        router.post(PLANNER_COMPOSE_URL).mock(return_value=Response(200, json=_good_plan_response(agent_id)))

        seed_task = asyncio.create_task(_seed_callback_loop(fake_db, mock_onix, agent_id))
        try:
            resp = await client.post("/api/plan", json={
                "prompt": "Resume este documento en español",
                "input_format": "text/plain",
                "output_format": "text/plain",
            })
        finally:
            seed_task.cancel()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan"] is not None
    assert body["plan"]["summary"] == "Summarize the document"
    assert body["plan"]["steps"][0]["recommended"]["agent_id"] == agent_id
    assert len(body["transaction_ids"]) == 1


async def test_plan_returns_error_when_no_candidates(client, fake_db, mock_onix):
    """No on_discover seeded -> discover times out -> empty candidates -> error string."""
    # Use a short DISCOVER_TIMEOUT_S to keep this test fast
    import app.config as bap_config
    original_timeout = bap_config.DISCOVER_TIMEOUT_S
    bap_config.DISCOVER_TIMEOUT_S = 1.0

    try:
        with respx_lib.mock(assert_all_called=False) as router:
            router.post(PLANNER_EXTRACT_URL).mock(return_value=Response(200, json=_extract_response()))

            resp = await client.post("/api/plan", json={
                "prompt": "anything",
                "input_format": "text/plain",
                "output_format": "text/plain",
            })
    finally:
        bap_config.DISCOVER_TIMEOUT_S = original_timeout

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] is None
    assert "summarize" in body["error"]


async def test_plan_propagates_422_from_extract_skills(client, fake_db, mock_onix):
    """Planner rejects the prompt with 422 -> /api/plan surfaces 422."""
    with respx_lib.mock(assert_all_called=False) as router:
        router.post(PLANNER_EXTRACT_URL).mock(return_value=Response(
            422, json={"detail": "LLM returned unknown skill_id 'imaginary'"}
        ))

        resp = await client.post("/api/plan", json={
            "prompt": "do something weird",
            "input_format": "text/plain",
            "output_format": "text/plain",
        })

    assert resp.status_code == 422
    assert "imaginary" in str(resp.json())


async def test_plan_returns_503_when_planner_unreachable(client, fake_db, mock_onix):
    """Planner is unreachable -> /api/plan returns 503 PLANNER_UNREACHABLE."""
    with respx_lib.mock(assert_all_called=False) as router:
        router.post(PLANNER_EXTRACT_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        resp = await client.post("/api/plan", json={
            "prompt": "test",
            "input_format": "text/plain",
            "output_format": "text/plain",
        })

    assert resp.status_code == 503
    assert "PLANNER_UNREACHABLE" in str(resp.json())
