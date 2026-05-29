"""
Shared Pydantic models for the Planner pipeline.

Used by:
  - services/planner (the LLM service, two phases: extract-skills, compose-pipeline)
  - services/bap     (the orchestrator that exposes POST /api/plan to the frontend)

Conceptual flow:

  Frontend           BAP                       Planner (LLM service)
  ────────           ─────                     ─────────────────────
   PlanRequest ───►  /api/plan
                      │
                      ├─►  POST /extract-skills  (LLM #1)
                      │    ExtractSkillsRequest ─► ExtractSkillsResponse
                      │
                      ├─►  /api/contracts/discover  (per skill, async)
                      │    yields candidates: list[AgentCandidate]
                      │
                      ├─►  POST /compose-pipeline  (LLM #2 + validator)
                      │    ComposeRequest ─► Plan
                      │
   PlanResponse ◄────  full response

Field naming: snake_case (LLM tends to emit that under structured_output).

NOTE: do NOT add ``from __future__ import annotations`` to this file. FastAPI
introspects these models via ``Body(...)`` and Pydantic ``TypeAdapter`` —
forward references break that path with ``PydanticUserError: not fully
defined``. Use real types (Python 3.11+ supports ``list[X]``, ``X | None``).
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Phase 1 — Extract Skills ─────────────────────────────────

class SkillRequest(BaseModel):
    """A skill the planner thinks is needed for one step.

    Semantic-first model: ``description`` is what drives the discover
    semantic search. ``skill_id`` is just a free-text label the LLM picks
    (no longer constrained to a registry) — used as a dict key to group
    candidates and as a human-readable tag in the UI.
    """

    skill_id: str = Field(
        ...,
        description=(
            "Short free-text label the LLM chooses for this step (e.g. 'summarize', "
            "'ocr'). Used as a grouping key for candidates. NOT validated against any "
            "registry — the LLM can use registry hints or invent its own labels."
        ),
    )
    description: str = Field(
        ...,
        description=(
            "One-sentence description of the action this step performs, including "
            "domain, language, and format. Used as intent.textSearch on discover — "
            "must be specific enough for semantic search against agent catalogs "
            "(e.g. 'summarize a legal contract preserving regulatory clauses in Spanish')."
        ),
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Hints for discover, e.g. {'language': 'es', 'modality': 'pdf'}",
    )
    reason: str = Field(..., description="Why this skill is required by the user prompt")


class ExtractSkillsRequest(BaseModel):
    prompt: str
    input_format: str
    output_format: str


class ExtractSkillsResponse(BaseModel):
    skills_needed: list[SkillRequest]
    summary: str


# ── Candidate shape (input to compose-pipeline) ──────────────

class AgentCandidate(BaseModel):
    """
    Slimmed projection of AgentFacts for the planner LLM.

    Built by the BAP from the on_discover response. We pass a thin shape
    (not the full AgentFacts) to keep the LLM context small and focused.
    """

    agent_id: str
    name: str
    provider: str
    skill_ids: list[str] = Field(
        default_factory=list,
        description="IDs of skills this agent offers (from skills[].id)",
    )
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    input_schema: Optional[dict] = Field(
        default=None,
        description="Agent-level JSON Schema for input (AgentFacts.inputSchema)",
    )
    output_schema: Optional[dict] = Field(
        default=None,
        description="Agent-level JSON Schema for output (AgentFacts.outputSchema)",
    )
    pricing_value: float = 0.0
    pricing_currency: str = "USD"
    pricing_model: str = "per_task"
    max_latency_ms: int = 0
    accuracy: Optional[float] = None
    jurisdiction: Optional[str] = None

    model_config = {"extra": "allow"}


# ── Phase 3 — Compose Pipeline ───────────────────────────────

class ComposeRequest(BaseModel):
    """What the BAP sends to the planner after running discover per skill."""

    prompt: str
    candidates: dict[str, list[AgentCandidate]] = Field(
        ...,
        description="Map skill_id -> candidates returned by discover for that skill",
    )


class StepRecommendation(BaseModel):
    """The agent the planner recommends for a given step."""

    agent_id: str
    name: str
    provider: str
    cost: float
    currency: str
    latency_ms: int
    reason: str = Field(..., description="Why this agent was picked over alternatives")


class StepAlternative(BaseModel):
    """A swappable alternative for a step. Frontend renders these under the recommended."""

    agent_id: str
    name: str
    cost: float
    latency_ms: int
    note: str = Field(
        default="",
        description="Short reason why this is an alternative (e.g. 'cheaper but slower')",
    )


class PlanStep(BaseModel):
    id: str = Field(..., description="Step ID, e.g. 's1', 's2' — referenced by depends_on")
    skill_id: str
    depends_on: list[str] = Field(
        default_factory=list,
        description="Step IDs this step waits for (DAG dependencies)",
    )
    recommended: StepRecommendation
    alternatives: list[StepAlternative] = Field(default_factory=list)
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map input field name -> source. Source can be:\n"
            "  '$pipeline_input.<field>'  for the original user input,\n"
            "  '$steps.<step_id>.<field>' for a previous step output,\n"
            "  a literal value otherwise (e.g. 'es')."
        ),
    )


class PlanEstimates(BaseModel):
    total_cost: float
    currency: str
    max_latency_ms: int = Field(
        ...,
        description="Worst-case latency walking the DAG critical path",
    )
    steps_count: int


class Plan(BaseModel):
    """The final executable plan returned by compose-pipeline."""

    summary: str
    steps: list[PlanStep]
    estimates: PlanEstimates
    on_error: str = Field(
        default="fail_fast",
        description="Pipeline-wide error strategy: fail_fast | continue | retry",
    )


# ── BAP-facing (frontend ↔ BAP) ──────────────────────────────

class PlanRequest(BaseModel):
    """What the frontend sends to POST /api/plan."""

    prompt: str
    input_format: str = "text/plain"
    output_format: str = "text/plain"


class PlanResponse(BaseModel):
    """What the BAP returns to the frontend."""

    plan: Optional[Plan] = None
    error: Optional[str] = Field(
        default=None,
        description="Non-null when planning failed (e.g. no candidates for a required skill)",
    )
    transaction_ids: list[str] = Field(
        default_factory=list,
        description="IDs of the discover transactions used to build this plan — for audit",
    )
