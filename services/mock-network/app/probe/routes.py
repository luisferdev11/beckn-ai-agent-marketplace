"""Agent probe HTTP surface.

  POST /api/probes/{bpp_subscriber_id}/{beckn_id}/retry
        Run the FULL Beckn-flow probe on demand (consumes LLM tokens).

  GET  /api/probes/{bpp_subscriber_id}/{beckn_id}
        Probe history for an agent (most recent first).

No auth in this MVP, consistent with the rest of the mock-network surface.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.probe import repository, runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/probes", tags=["probe"])


@router.post("/{bpp_subscriber_id}/{beckn_id}/retry")
async def retry_probe(bpp_subscriber_id: str, beckn_id: str):
    """Re-run the full probe for one agent (Epic E7)."""
    agent = await repository.get_agent(bpp_subscriber_id, beckn_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "agent_not_found",
                    "bpp_subscriber_id": bpp_subscriber_id, "beckn_id": beckn_id},
        )
    result = await runner.probe_agent_full(agent)
    return result


@router.get("/{bpp_subscriber_id}/{beckn_id}")
async def probe_history(bpp_subscriber_id: str, beckn_id: str):
    agent = await repository.get_agent(bpp_subscriber_id, beckn_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "agent_not_found",
                    "bpp_subscriber_id": bpp_subscriber_id, "beckn_id": beckn_id},
        )
    probes = await repository.list_probes(bpp_subscriber_id, beckn_id)
    return {
        "bpp_subscriber_id": bpp_subscriber_id,
        "beckn_id": beckn_id,
        "probe_status": agent.get("probe_status"),
        "probes": probes,
    }
