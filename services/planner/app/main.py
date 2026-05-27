"""Planner service entrypoint.

Two endpoints power the buyer-side planning flow:
  POST /extract-skills   — Phase 1: NL prompt -> needed skills + filter hints
  POST /compose-pipeline — Phase 3: candidates -> validated executable plan
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException

from app import config, engine, validator
from beckn_models.planning import (
    ComposeRequest,
    ExtractSkillsRequest,
    ExtractSkillsResponse,
    Plan,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Agent Planner",
    version=config.PLANNER_VERSION,
    description=(
        "Two-phase planner: extract skills from a prompt, then compose a "
        "concrete pipeline from candidate agents."
    ),
)

START_TIME = time.time()


@app.post("/extract-skills", response_model=ExtractSkillsResponse)
async def extract_skills_endpoint(req: ExtractSkillsRequest) -> ExtractSkillsResponse:
    """Phase 1 — NL prompt to a list of skills with filter hints (no agents yet)."""
    try:
        return await engine.extract_skills(req)
    except ValueError as exc:
        # Hallucinated skill ID or empty response from the LLM
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("extract_skills failed")
        raise HTTPException(
            status_code=503,
            detail=f"PLANNER_LLM_ERROR: {exc}",
        )


@app.post("/compose-pipeline", response_model=Plan)
async def compose_pipeline_endpoint(req: ComposeRequest) -> Plan:
    """Phase 3 — candidates + prompt -> validated executable plan.

    Runs the LLM compose call, validates the structural correctness, retries
    once with the errors as context if validation fails. If the retry also
    produces an invalid plan, returns 422 so the BAP can surface a clear
    message to the frontend.
    """
    try:
        plan = await engine.compose_pipeline(req)
    except Exception as exc:
        logger.exception("compose first call failed")
        raise HTTPException(status_code=503, detail=f"PLANNER_LLM_ERROR: {exc}")

    errors = validator.validate_plan(plan, req.candidates)

    if errors and config.COMPOSE_RETRY_ON_VALIDATION_FAILURE:
        logger.warning(
            "Plan validation failed (%d errors). Retrying with error context.",
            len(errors),
        )
        retry_hint = (
            "\n\nIMPORTANT: your previous attempt had these validation errors. "
            "Fix them all in your new output:\n"
            + "\n".join(f"  - [{e.code}] {e.message}" for e in errors)
        )
        try:
            plan = await engine.compose_pipeline(req, retry_hint=retry_hint)
            errors = validator.validate_plan(plan, req.candidates)
        except Exception as exc:
            logger.exception("compose retry failed")
            raise HTTPException(
                status_code=503,
                detail=f"PLANNER_LLM_ERROR: {exc}",
            )

    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PLAN",
                "message": "Planner could not produce a valid plan after retry",
                "errors": [
                    {"code": e.code, "message": e.message, "step_id": e.step_id}
                    for e in errors
                ],
            },
        )

    return plan


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": config.SERVICE_NAME,
        "version": config.PLANNER_VERSION,
        "uptime_seconds": int(time.time() - START_TIME),
        "model": config.PLANNER_MODEL,
    }
