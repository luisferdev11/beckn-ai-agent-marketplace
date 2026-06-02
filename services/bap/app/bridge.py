"""Bridge: convert Planner Plan → Orchestrator v2 execution plan.

The planner produces a ``Plan`` with steps, dependencies, and agent
recommendations.  Orchestrator v2 expects a flat dict with ``agents``,
``steps`` (with ``${…}`` interpolation), ``executionLayers``, and
``finalOutput``.  This module performs the translation.

Agent *endpoints* are intentionally left empty (``""``) — the BPP fills
them in from its own database before passing the plan to orchestrator v2.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from beckn_models.planning import Plan


# ── Public API ────────────────────────────────────────────────────────────────

def build_orchestrator2_plan(
    plan: Plan,
    agent_facts: dict[str, dict],
    user_input: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    """Return a dict ready for ``POST /execute`` on orchestrator v2.

    Parameters
    ----------
    plan:
        The ``Plan`` returned by the planner ``/compose-pipeline`` phase.
    agent_facts:
        Mapping *agent_id → resourceAttributes* (full AgentFacts dicts)
        extracted from the ``on_discover`` callbacks.
    user_input:
        Structured user input (e.g. ``{"review": "I ordered…"}``).
    prompt:
        Original natural-language prompt from the user.
    """
    agents = _build_agents(plan, agent_facts)
    steps = _build_steps(plan)
    layers = _build_execution_layers(plan)
    final_output = _build_final_output(plan, agent_facts)

    return {
        "goal": plan.summary,
        "userInput": user_input,
        "agents": agents,
        "steps": steps,
        "executionLayers": layers,
        "finalOutput": final_output,
    }


# ── Agents ────────────────────────────────────────────────────────────────────

def _build_agents(plan: Plan, agent_facts: dict[str, dict]) -> list[dict]:
    """One entry per unique recommended agent across all steps."""
    seen: set[str] = set()
    agents: list[dict] = []

    for step in plan.steps:
        aid = step.recommended.agent_id
        if aid in seen:
            continue
        seen.add(aid)

        facts = agent_facts.get(aid, {})
        skills_raw = facts.get("skills", [])

        # provider.url from AgentFacts — used as fallback endpoint hint
        # when the BPP doesn't have this agent in its own DB (cross-BPP).
        provider_url = ""
        prov = facts.get("provider", {})
        if isinstance(prov, dict):
            provider_url = prov.get("url", "")

        agents.append({
            "agent_name": aid,
            "label": facts.get("label", step.recommended.name),
            "description": facts.get("description", ""),
            # BPP fills these in from its DB; provider_url is a fallback
            # for cross-BPP agents the executing BPP doesn't own.
            "endpoint": "",
            "provider_url": provider_url,
            "method": "POST",
            "inputSchema": facts.get("inputSchema") or facts.get("input_schema", {}),
            "outputSchema": facts.get("outputSchema") or facts.get("output_schema", {}),
            "skills": [
                {
                    "id": s.get("id", ""),
                    "description": s.get("description", ""),
                    "inputModes": s.get("inputModes", []),
                    "outputModes": s.get("outputModes", []),
                }
                for s in skills_raw
                if isinstance(s, dict)
            ],
            "capabilities": facts.get("capabilities", {"modalities": ["text"], "streaming": False}),
        })

    return agents


# ── Steps ─────────────────────────────────────────────────────────────────────

def _translate_input_mapping(mapping: dict[str, str]) -> dict[str, Any]:
    """Convert planner input_mapping to orchestrator v2 interpolation syntax.

    Planner format:
        ``$pipeline_input.field``  → orch2: ``${input.field}``
        ``$steps.s1.field``        → orch2: ``${s1.field}``
        anything else              → literal value
    """
    translated: dict[str, Any] = {}
    for key, value in mapping.items():
        if not isinstance(value, str):
            translated[key] = value
            continue
        if value.startswith("$pipeline_input."):
            field = value[len("$pipeline_input."):]
            translated[key] = f"${{input.{field}}}"
        elif value.startswith("$steps."):
            # "$steps.s1.field" → "${s1.field}"
            rest = value[len("$steps."):]
            translated[key] = f"${{{rest}}}"
        else:
            # Literal value
            translated[key] = value
    return translated


def _build_steps(plan: Plan) -> list[dict]:
    steps: list[dict] = []
    for s in plan.steps:
        steps.append({
            "id": s.id,
            "agent": s.recommended.agent_id,
            # BPP fills this in.
            "endpoint": "",
            "input": _translate_input_mapping(s.input_mapping),
            "dependsOn": s.depends_on,
            "rationale": s.recommended.reason,
        })
    return steps


# ── Execution layers (topological sort) ──────────────────────────────────────

def _build_execution_layers(plan: Plan) -> list[list[str]]:
    """Kahn's algorithm: group steps into parallel batches respecting deps."""
    step_ids = [s.id for s in plan.steps]
    deps: dict[str, list[str]] = {s.id: list(s.depends_on) for s in plan.steps}
    in_degree: dict[str, int] = {sid: len(deps[sid]) for sid in step_ids}

    layers: list[list[str]] = []
    remaining = set(step_ids)

    while remaining:
        # Steps with no unresolved dependencies form the next layer
        layer = sorted(sid for sid in remaining if in_degree[sid] == 0)
        if not layer:
            # Cycle detected — dump everything remaining into one layer
            layers.append(sorted(remaining))
            break
        layers.append(layer)
        for sid in layer:
            remaining.discard(sid)
            # Decrement in-degree of dependents
            for other in step_ids:
                if other in remaining and sid in deps[other]:
                    in_degree[other] -= 1

    return layers


# ── Final output template ─────────────────────────────────────────────────────

def _build_final_output(plan: Plan, agent_facts: dict[str, dict]) -> dict[str, str]:
    """Auto-generate a finalOutput template from the last layer's output schemas.

    For each step in the last execution layer, map every key in the agent's
    outputSchema.properties to ``${stepId.key}``.
    """
    layers = _build_execution_layers(plan)
    if not layers:
        return {}

    last_layer_ids = set(layers[-1])
    step_agent: dict[str, str] = {s.id: s.recommended.agent_id for s in plan.steps}

    output: dict[str, str] = {}
    for sid in sorted(last_layer_ids):
        aid = step_agent.get(sid, "")
        facts = agent_facts.get(aid, {})
        out_schema = facts.get("outputSchema") or facts.get("output_schema", {})
        props = out_schema.get("properties", {})
        if props:
            for key in props:
                output[key] = f"${{{sid}.{key}}}"
        else:
            # Fallback: reference the whole step output as "result"
            output[f"{sid}_result"] = f"${{{sid}}}"

    return output
