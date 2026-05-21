"""Planner — decomposes a user prompt into an ordered sequence of skills."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from app.planner_models import Plan

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("PLANNER_MODEL", "llama-3.3-70b-versatile")

_SKILLS_PATH = Path(__file__).parent / "skills_registry.json"

SYSTEM_PROMPT = """\
You are a task planner for an AI agent marketplace.

Your job: given a user request, decompose it into an ordered sequence of skills.
Each step must reference exactly one skill from the available registry.
If the task can be done with a single skill, return a single step.
Only use skills from the registry below — never invent new ones.

AVAILABLE SKILLS:
{skills_block}

RULES:
- Prefer the FEWEST steps possible. Do not add intermediate steps unless the user explicitly asks for them or the task genuinely cannot be done with fewer skills.
- A single skill that directly fulfills the user request is always preferred over a multi-step chain.
- Only add a step when its output is strictly required as input for a subsequent step and no single skill can cover both.
- Assume every skill can handle the declared input_format natively. Do NOT add preprocessing steps (like ocr) unless the user explicitly asks for text extraction or the task requires a capability that the main skill clearly cannot provide.
- Each step has: "step" (int starting at 1), "skill_id" (from registry), "reason" (why this step is needed).
- Include a "summary" field with a one-line description of the full plan.
- The user will declare their desired input_format and output_format. Use them to understand the task, but do NOT include them in the plan steps.
"""

USER_TEMPLATE = """\
User request: {prompt}
Input format: {input_format}
Output format: {output_format}
"""


def _load_skills() -> list[dict]:
    with open(_SKILLS_PATH) as f:
        data = json.load(f)
    return data["skills"]


def _build_skills_block(skills: list[dict]) -> str:
    lines = [f'- {s["id"]}: {s["description"]}' for s in skills]
    return "\n".join(lines)


def _get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model_name=MODEL_NAME,
        temperature=0,
    )


_prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", USER_TEMPLATE),
])


async def generate_plan(prompt: str, input_format: str, output_format: str) -> Plan:
    """Call the LLM to produce an execution plan from a user prompt."""
    skills = _load_skills()
    skills_block = _build_skills_block(skills)
    valid_ids = {s["id"] for s in skills}

    llm = _get_llm().with_structured_output(Plan)
    chain = _prompt | llm

    plan = await chain.ainvoke({
        "skills_block": skills_block,
        "prompt": prompt,
        "input_format": input_format,
        "output_format": output_format,
    })

    for step in plan.steps:
        if step.skill_id not in valid_ids:
            raise ValueError(
                f"LLM returned unknown skill_id '{step.skill_id}'. "
                f"Valid: {sorted(valid_ids)}"
            )

    return plan
