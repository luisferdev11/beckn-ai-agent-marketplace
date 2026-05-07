"""Thin async client for the orchestrator service."""

import logging

import httpx

from app.config import ORCHESTRATOR_URL

logger = logging.getLogger(__name__)


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
