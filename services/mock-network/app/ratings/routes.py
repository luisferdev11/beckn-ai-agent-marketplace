"""CDS HTTP surface — ratings ingest.

BPPs that receive an on-network ``rate`` event POST a normalised
summary here so the marketplace-side aggregate stays consistent. Why a
dedicated endpoint rather than re-using a Beckn verb: this is a B2B
side-channel between BPP backends and the CDS, not a buyer-facing
interaction. Wrapping it in a Beckn envelope would add ceremony with
no observable benefit.

Endpoint:

  POST /cds/ratings/ingest
    {
      "bppSubscriberId": "bpp.example.com",
      "agentBecknId":   "agent-summarizer-001",
      "score":           4.5,
      "scoreMin":        1.0,
      "scoreMax":        5.0
    }

Validation:
  - all four numeric fields required and in [scoreMin, scoreMax].
  - bppSubscriberId and agentBecknId non-empty strings.
  - 422 on missing / out-of-range / wrong shape.

The endpoint is purely additive — re-posting the same rating event
adds another sample to the rolling sum/count. De-duplication (if
needed at scale) is the BPP's job because only the BPP knows whether
the same buyer re-rated or whether a retry duplicate fired.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ratings import repository as ratings_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cds/ratings", tags=["cds-ratings"])


class RatingIngestRequest(BaseModel):
    bppSubscriberId: str = Field(..., min_length=1)
    agentBecknId: str = Field(..., min_length=1)
    score: float
    scoreMin: float = 1.0
    scoreMax: float = 5.0


@router.post("/ingest")
async def ingest(req: RatingIngestRequest) -> dict:
    if req.scoreMin >= req.scoreMax:
        raise HTTPException(
            status_code=422,
            detail=[{
                "type": "value_error",
                "loc": ["body", "scoreMin"],
                "msg": "scoreMin must be strictly less than scoreMax",
            }],
        )
    if not (req.scoreMin <= req.score <= req.scoreMax):
        raise HTTPException(
            status_code=422,
            detail=[{
                "type": "value_error",
                "loc": ["body", "score"],
                "msg": f"score must be within [{req.scoreMin}, {req.scoreMax}]",
                "input": req.score,
            }],
        )

    row = await ratings_repo.ingest_rating(
        bpp_subscriber_id=req.bppSubscriberId,
        agent_beckn_id=req.agentBecknId,
        score=float(req.score),
    )
    logger.info(
        "rating ingested: bpp=%s agent=%s score=%.2f count=%s avg=%s",
        req.bppSubscriberId, req.agentBecknId, req.score,
        row.get("rating_count"), row.get("avg_score"),
    )
    return {
        "status": "ok",
        "aggregate": {
            "bppSubscriberId": req.bppSubscriberId,
            "agentBecknId":    req.agentBecknId,
            "ratingCount":     row.get("rating_count"),
            "avgScore":        float(row.get("avg_score") or 0.0),
        },
    }


@router.get("/aggregate")
async def aggregate(bppSubscriberId: str, agentBecknId: str) -> dict:
    """Operator/debug endpoint: read the current aggregate for one agent."""
    row = await ratings_repo.get_aggregate(
        bpp_subscriber_id=bppSubscriberId,
        agent_beckn_id=agentBecknId,
    )
    if not row:
        return {
            "bppSubscriberId": bppSubscriberId,
            "agentBecknId":    agentBecknId,
            "ratingCount":     0,
            "avgScore":        0.0,
        }
    return {
        "bppSubscriberId": row["bpp_subscriber_id"],
        "agentBecknId":    row["agent_beckn_id"],
        "ratingCount":     row["rating_count"],
        "avgScore":        float(row["avg_score"]),
    }
