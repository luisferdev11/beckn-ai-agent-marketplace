"""Thin async client for the orchestrator services (v1 and v2)."""

import logging

import httpx

from app.config import ORCHESTRATOR_URL, ORCHESTRATOR2_URL

logger = logging.getLogger(__name__)


# ── Orchestrator v1 (single-agent, fire & forget) ────────────────────────────

async def start_execution(payload: dict) -> dict:
    """POST /execute → returns {"execution_id": ..., "status": "PENDING"}"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(f"{ORCHESTRATOR_URL}/execute", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_execution(execution_id: str) -> dict:
    """GET /execute/{execution_id} → returns full ExecuteResponse"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{ORCHESTRATOR_URL}/execute/{execution_id}")
        resp.raise_for_status()
        return resp.json()


# ── Orchestrator v2 (multi-agent pipeline) ────────────────────────────────────

async def start_pipeline(plan: dict, prompt: str, data: dict) -> dict:
    """POST /execute to orchestrator v2.

    Returns {"execution_id": ..., "status": "PENDING"}.
    """
    payload = {"plan": plan, "prompt": prompt, "data": data}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{ORCHESTRATOR2_URL}/execute", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_pipeline_execution(execution_id: str) -> dict:
    """GET /execute/{id} from orchestrator v2.

    Returns {"execution_id", "status", "goal", "result", "execution_summary"}.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{ORCHESTRATOR2_URL}/execute/{execution_id}")
        resp.raise_for_status()
        return resp.json()
