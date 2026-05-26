"""Pydantic models for the planner input/output contract."""
from __future__ import annotations

from pydantic import BaseModel


class PlanRequest(BaseModel):
    """What the user sends to the planner."""
    prompt: str
    input_format: str
    output_format: str


class PlanStep(BaseModel):
    """A single step in the execution plan."""
    step: int
    skill_id: str
    reason: str


class Plan(BaseModel):
    """The planner output: an ordered sequence of skills."""
    steps: list[PlanStep]
    summary: str
