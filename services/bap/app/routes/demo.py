"""HTTP surface for the Story 1 cross-BPP demo.

Two endpoints:

  GET  /api/demo/spec
      Returns the controlled demo's static contract — the agents we
      run, their BPPs, the JSON Schemas the orchestrator enforces, the
      sample document, and the prompt sent to the planner. The
      frontend reads this to pre-fill its demo page so the UI and the
      runtime can't drift.

  POST /api/demo/legal-pipeline
      Runs the full pipeline (discover → planner → step 1 → step 2)
      and returns a structured trace plus the final result. The body
      is the user's document and language. Errors at any layer are
      surfaced in the trace, not as HTTP 500s — the UI should always
      get a response it can render.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.demo import runner, specs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])


# ── /spec ──────────────────────────────────────────────────────────


@router.get("/spec")
async def get_spec() -> dict:
    """Return the frozen demo contract (agents, schemas, sample doc)."""
    return {
        "prompt": specs.DEMO_PROMPT,
        "sample_document": specs.SAMPLE_DOCUMENT,
        "pipeline": [
            {
                "step_id": step.step_id,
                "skill_id": step.skill_id,
                "agent_id": step.agent_id,
                "bpp_id": step.bpp_id,
                "bpp_uri": step.bpp_uri,
                "description": step.description,
                "input_schema": step.input_schema,
                "output_schema": step.output_schema,
            }
            for step in specs.PIPELINE
        ],
        "step_input_mapping": specs.STEP2_INPUT_MAPPING,
    }


# ── /legal-pipeline ────────────────────────────────────────────────


class LegalPipelineRequest(BaseModel):
    document: str = Field(..., min_length=1)
    # ISO-639-1; the summarizer accepts en|hi|es per its declared
    # supportedLanguages. Default English to match Story 1.
    language: str = Field("en", min_length=2, max_length=8)


@router.post("/legal-pipeline")
async def run_legal_pipeline(req: LegalPipelineRequest) -> dict:
    """Execute the Story 1 pipeline against the live Beckn stack.

    The runner returns a ``DemoResult`` dataclass; we serialise it
    explicitly so the on-the-wire shape stays stable as the runner
    grows new fields (don't lean on ``asdict`` for the top level —
    we want the response keys to be camel-friendly).
    """
    result = await runner.run_demo(document=req.document, language=req.language)

    return {
        "overall_status": result.overall_status,
        "discover": asdict(result.discover),
        "planner": asdict(result.planner),
        "steps": [asdict(s) for s in result.steps],
        "final_output": result.final_output,
    }
