"""Bridge: convert Planner Plan + discover data → pipeline execution plan.

The planner produces a ``Plan`` with steps, dependencies, and agent
recommendations.  This module translates it into a flat execution plan
that the BAP-side pipeline executor can drive step-by-step through
individual Beckn contracts (select → init → confirm → status per agent).

Each step carries the BPP routing info (bpp_id, bpp_uri, offer_id)
extracted from the on_discover callbacks so the executor targets the
correct provider for each agent.
"""

from __future__ import annotations

from typing import Any

from beckn_models.planning import Plan


# ── Public API ────────────────────────────────────────────────────────────────

def build_pipeline_plan(
    plan: Plan,
    agent_catalog: dict[str, dict],
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Return a pipeline execution plan for the BAP-side executor.

    Parameters
    ----------
    plan:
        The ``Plan`` returned by the planner ``/compose-pipeline`` phase.
    agent_catalog:
        Mapping *agent_id → catalog info* extracted from on_discover callbacks.
        Each entry has: resourceAttributes, bpp_id, bpp_uri, offer_id.
    user_input:
        Structured user input (e.g. ``{"document": "...", "text": "..."}``).
    """
    steps = _build_steps(plan, agent_catalog)
    layers = _build_execution_layers(plan)

    return {
        "summary": plan.summary,
        "user_input": user_input,
        "steps": steps,
        "execution_layers": layers,
    }


# ── Steps ─────────────────────────────────────────────────────────────────────

def _build_steps(plan: Plan, agent_catalog: dict[str, dict]) -> list[dict]:
    steps: list[dict] = []
    for s in plan.steps:
        aid = s.recommended.agent_id
        cat = agent_catalog.get(aid, {})
        ra = cat.get("resourceAttributes", {})

        steps.append({
            "id": s.id,
            "agent_id": aid,
            "agent_name": s.recommended.name,
            "bpp_id": cat.get("bpp_id", ""),
            "bpp_uri": cat.get("bpp_uri", ""),
            "offer_id": cat.get("offer_id", f"offer-{aid}"),
            "input_mapping": s.input_mapping,
            "input_schema": ra.get("inputSchema") or ra.get("input_schema"),
            "output_schema": ra.get("outputSchema") or ra.get("output_schema"),
            "depends_on": s.depends_on,
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
        layer = sorted(sid for sid in remaining if in_degree[sid] == 0)
        if not layer:
            layers.append(sorted(remaining))
            break
        layers.append(layer)
        for sid in layer:
            remaining.discard(sid)
            for other in step_ids:
                if other in remaining and sid in deps[other]:
                    in_degree[other] -= 1

    return layers
