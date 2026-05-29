"""
LLM engine — two-phase planning.

Phase 1 (extract_skills): prompt + format hints -> list of skills with filter hints.
Phase 2 (handled by BAP):  for each skill, BAP runs discover and collects candidates.
Phase 3 (compose_pipeline): prompt + candidates -> executable Plan.

Both phases use Groq + Llama 3.3 with structured output bound to Pydantic models.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from app import config
from beckn_models.planning import (
    AgentCandidate,
    ComposeRequest,
    ExtractSkillsRequest,
    ExtractSkillsResponse,
    Plan,
)

logger = logging.getLogger(__name__)

_SKILLS_PATH = Path(__file__).parent / "skills_registry.json"


# ── LLM construction ─────────────────────────────────────────

def _llm() -> ChatGroq:
    return ChatGroq(
        api_key=config.GROQ_API_KEY,
        model_name=config.PLANNER_MODEL,
        temperature=0,
        timeout=config.LLM_TIMEOUT_S,
    )


def _load_skills() -> list[dict]:
    with open(_SKILLS_PATH) as f:
        data = json.load(f)
    return data["skills"]


def _build_skills_block(skills: list[dict]) -> str:
    return "\n".join(f'- {s["id"]}: {s["description"]}' for s in skills)


# ── Phase 1 — Extract Skills ─────────────────────────────────

EXTRACT_SYSTEM_PROMPT = """\
You are the intent parser for an AI agent marketplace.

Given a user request, identify which steps (skills) are needed to fulfill it.
You DO NOT pick concrete agents — agent selection happens later from the discover results.

COMMON SKILL LABELS (inspiration, not a constraint — pick one of these when it fits,
or use your own short label if none matches):
{skills_block}

For each step you produce, you MUST fill these fields:

  skill_id:    A short free-text label that captures the action (e.g. "summarize",
               "ocr", "translate"). Used to group candidates — does not have to come
               from the list above.

  description: ONE sentence describing the action including domain, language, and
               format. This sentence IS the semantic search query against agent
               catalogs — be specific and use vocabulary catalog entries would
               use. GOOD:  "summarize a legal contract preserving regulatory
                           clauses, in Spanish"
                           "extract line items, totals and vendor from an invoice PDF"
               BAD:   "do summary"        (too vague)
                      "skill: summarize"  (just repeats the label)

  filters:     Structured hints. Use these keys when implied by the prompt:
                 language     e.g. "es", "en", "hi"
                 modality     e.g. "pdf", "image", "text"
                 jurisdiction e.g. "IN", "EU", "US"

  reason:      One sentence explaining why this step is part of the pipeline
               (read by humans in logs and the UI; do NOT repeat the description).

RULES:
- Use the FEWEST steps possible. A single-step solution is preferred when correct.
- Order skills_needed in natural execution order (input -> processing -> output).
- `summary` is one human-readable sentence describing the overall task.
"""

EXTRACT_USER_TEMPLATE = """\
User request: {prompt}
Declared input format: {input_format}
Desired output format: {output_format}
"""

_extract_prompt = ChatPromptTemplate.from_messages([
    ("system", EXTRACT_SYSTEM_PROMPT),
    ("human", EXTRACT_USER_TEMPLATE),
])


async def extract_skills(req: ExtractSkillsRequest) -> ExtractSkillsResponse:
    """Phase 1: NL prompt -> list of needed steps with semantic search descriptions.

    Skill IDs are NOT validated against a registry. The registry is loaded only
    as inspiration content for the system prompt — the LLM is allowed to invent
    labels. Validation that "this skill has candidates" happens post-discover
    when the BAP sees an empty result for some skill_id.
    """
    skills = _load_skills()
    skills_block = _build_skills_block(skills)

    chain = _extract_prompt | _llm().with_structured_output(ExtractSkillsResponse)
    resp: ExtractSkillsResponse = await chain.ainvoke({
        "skills_block": skills_block,
        "prompt": req.prompt,
        "input_format": req.input_format,
        "output_format": req.output_format,
    })

    if not resp.skills_needed:
        raise ValueError("LLM returned no skills — cannot proceed with empty plan")

    return resp


# ── Phase 3 — Compose Pipeline ───────────────────────────────

COMPOSE_SYSTEM_PROMPT = """\
You are a pipeline composer for an AI agent marketplace.

Given a user prompt and concrete candidate agents per skill, build an executable plan.
Each step picks ONE agent as `recommended` and lists the others as `alternatives`.

User prompt:
{prompt}

CANDIDATES BY SKILL:
{candidates_block}

RULES:
1. Create exactly one step per skill needed. Step IDs are "s1", "s2", ... in execution order.
2. For each step, pick the `recommended` agent giving priority to (in order):
     - matches required language
     - matches required modality (input_modes / output_modes)
     - lowest price
     - lowest latency
     - highest accuracy
3. List the OTHER candidates of the same skill as `alternatives` with a short `note` explaining the tradeoff (e.g. "cheaper but slower", "no Spanish support").
4. Set `depends_on` to the step IDs whose output this step needs. Independent steps have depends_on=[].
5. Build `input_mapping`:
   - Source format (the value side of each mapping entry):
       "$pipeline_input.<field>"     → the user's original input (shape unknown at plan time)
       "$steps.<id>.<field>"         → output of a previous step (must be in depends_on)
       any other literal string      → constant value (ALWAYS treated as type 'string')
   - You MUST map EVERY required input field of the recommended agent. Required
     fields are marked with '!' in the `input=` schema shown above (e.g. `text!:string`
     means `text` is required and its type is string).
   - When using "$steps.X.Y", `Y` MUST be a field that exists in agent X's `output=`
     schema, and its type MUST be compatible with the target input field's type.
     Compatibility rule: same type, OR source is 'integer' and target is 'number'.
   - When using a literal string, the target input field MUST accept type 'string'.
     Do NOT put numeric literals like "5" into integer/number fields — the value
     is a string, not the number.
   - You MUST list the source step ID in depends_on whenever you reference its output.
6. Compute `estimates`:
   - total_cost = sum of recommended agent costs
   - max_latency_ms = longest dependency chain latency
   - currency = currency of the recommended agents (assume consistent across steps)
   - steps_count = number of steps
7. `summary` is one sentence describing the pipeline.
8. NEVER reference an agent_id that isn't in the candidates above. The system will reject your output if you do.
9. Set on_error to "fail_fast" by default.
"""

COMPOSE_USER_TEMPLATE = """\
Produce the plan as structured JSON.
{retry_hint}
"""


def _format_schema(schema: dict | None) -> str:
    """Render a JSON Schema as `{field!:type, ...}` (`!` marks required)."""
    if not schema or not isinstance(schema.get("properties"), dict):
        return "{}"
    required = set(schema.get("required") or [])
    parts: list[str] = []
    for name, spec in schema["properties"].items():
        type_spec = spec.get("type", "any") if isinstance(spec, dict) else "any"
        if isinstance(type_spec, list):
            type_str = "|".join(type_spec)
        else:
            type_str = str(type_spec)
        marker = "!" if name in required else ""
        parts.append(f"{name}{marker}:{type_str}")
    return "{" + ", ".join(parts) + "}"


def _format_candidate(c: AgentCandidate) -> str:
    return (
        f"  - id={c.agent_id} name={c.name!r} provider={c.provider!r} "
        f"price={c.pricing_value}{c.pricing_currency} latency={c.max_latency_ms}ms "
        f"langs={c.supported_languages} "
        f"input={_format_schema(c.input_schema)} "
        f"output={_format_schema(c.output_schema)}"
    )


def _build_candidates_block(candidates: dict[str, list[AgentCandidate]]) -> str:
    lines: list[str] = []
    for skill_id, agents in candidates.items():
        lines.append(f"\nSkill: {skill_id}")
        for a in agents:
            lines.append(_format_candidate(a))
    return "\n".join(lines)


_compose_prompt = ChatPromptTemplate.from_messages([
    ("system", COMPOSE_SYSTEM_PROMPT),
    ("human", COMPOSE_USER_TEMPLATE),
])


async def compose_pipeline(req: ComposeRequest, retry_hint: str = "") -> Plan:
    """Phase 3: candidates + prompt -> executable Plan. Pure LLM, no validation."""
    candidates_block = _build_candidates_block(req.candidates)

    chain = _compose_prompt | _llm().with_structured_output(Plan)
    plan: Plan = await chain.ainvoke({
        "prompt": req.prompt,
        "candidates_block": candidates_block,
        "retry_hint": retry_hint,
    })

    if not plan.steps:
        raise ValueError("LLM returned an empty plan (no steps)")

    return plan
