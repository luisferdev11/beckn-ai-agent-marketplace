"""
Plan validation — runs after the LLM compose call.

Catches LLM hallucinations and structural errors before the plan reaches
the BAP. If any check fails, the orchestrator retries the compose call
once with the errors as context.

Checks (in order):
  1. Step IDs are unique
  2. depends_on references existing step IDs
  3. No cycles (DAG)
  4. recommended.agent_id is in candidates for the step's skill
  5. Each alternative.agent_id is in candidates for the step's skill
  6. input_mapping references are well-formed and depend on declared steps
  7. input_mapping source fields exist in the previous step's output_schema
  8. Every required input field of the target agent is mapped
  9. Source-field type is compatible with target-field type (JSON Schema)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from beckn_models.planning import AgentCandidate, Plan


@dataclass
class ValidationError:
    code: str
    message: str
    step_id: Optional[str] = None


def validate_plan(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    """Run all checks. Returns list of errors; empty list = valid."""
    errors: list[ValidationError] = []
    errors.extend(_check_step_ids_unique(plan))
    errors.extend(_check_depends_on_refs(plan))
    if not errors:
        errors.extend(_check_no_cycles(plan))
    errors.extend(_check_recommended_in_candidates(plan, candidates))
    errors.extend(_check_alternatives_in_candidates(plan, candidates))
    errors.extend(_check_input_mappings(plan, candidates))
    errors.extend(_check_required_inputs_mapped(plan, candidates))
    errors.extend(_check_mapping_types(plan, candidates))
    return errors


def _check_step_ids_unique(plan: Plan) -> list[ValidationError]:
    seen: set[str] = set()
    errors: list[ValidationError] = []
    for step in plan.steps:
        if step.id in seen:
            errors.append(ValidationError(
                code="DUPLICATE_STEP_ID",
                message=f"Step ID '{step.id}' appears more than once",
                step_id=step.id,
            ))
        seen.add(step.id)
    return errors


def _check_depends_on_refs(plan: Plan) -> list[ValidationError]:
    ids = {s.id for s in plan.steps}
    errors: list[ValidationError] = []
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in ids:
                errors.append(ValidationError(
                    code="UNKNOWN_DEPENDS_ON",
                    message=(
                        f"Step '{step.id}' depends on '{dep}' which is not "
                        f"defined in the plan"
                    ),
                    step_id=step.id,
                ))
    return errors


def _check_no_cycles(plan: Plan) -> list[ValidationError]:
    """Kahn's algorithm — if we can't visit all nodes, there's a cycle."""
    in_degree: dict[str, int] = {s.id: len(s.depends_on) for s in plan.steps}
    successors: dict[str, list[str]] = {s.id: [] for s in plan.steps}
    for step in plan.steps:
        for dep in step.depends_on:
            if dep in successors:
                successors[dep].append(step.id)

    queue = [sid for sid, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        sid = queue.pop(0)
        visited += 1
        for succ in successors[sid]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    if visited != len(plan.steps):
        return [ValidationError(
            code="CYCLE_DETECTED",
            message="The plan contains a dependency cycle (depends_on must form a DAG)",
        )]
    return []


def _check_recommended_in_candidates(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for step in plan.steps:
        candidate_ids = {c.agent_id for c in candidates.get(step.skill_id, [])}
        if not candidate_ids:
            errors.append(ValidationError(
                code="NO_CANDIDATES_FOR_SKILL",
                message=(
                    f"Step '{step.id}': no candidates were provided for skill "
                    f"'{step.skill_id}' — the LLM should not have picked this skill"
                ),
                step_id=step.id,
            ))
            continue
        if step.recommended.agent_id not in candidate_ids:
            errors.append(ValidationError(
                code="RECOMMENDED_NOT_IN_CANDIDATES",
                message=(
                    f"Step '{step.id}': recommended agent "
                    f"'{step.recommended.agent_id}' is not among the candidates "
                    f"for skill '{step.skill_id}'. Available: {sorted(candidate_ids)}"
                ),
                step_id=step.id,
            ))
    return errors


def _check_alternatives_in_candidates(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for step in plan.steps:
        candidate_ids = {c.agent_id for c in candidates.get(step.skill_id, [])}
        for alt in step.alternatives:
            if alt.agent_id not in candidate_ids:
                errors.append(ValidationError(
                    code="ALTERNATIVE_NOT_IN_CANDIDATES",
                    message=(
                        f"Step '{step.id}': alternative '{alt.agent_id}' is not "
                        f"in candidates for skill '{step.skill_id}'"
                    ),
                    step_id=step.id,
                ))
    return errors


def _check_input_mappings(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    """
    For every $steps.<id>.<field> reference, verify:
      - the referenced step exists
      - the current step declares it in depends_on
      - if the referenced agent's output_schema declares properties, the field is among them
    """
    errors: list[ValidationError] = []
    step_by_id = {s.id: s for s in plan.steps}
    agent_by_id: dict[str, AgentCandidate] = {
        c.agent_id: c for cs in candidates.values() for c in cs
    }

    for step in plan.steps:
        for input_field, source in step.input_mapping.items():
            if not isinstance(source, str) or not source.startswith("$steps."):
                continue
            ref = source[len("$steps."):]
            parts = ref.split(".", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                errors.append(ValidationError(
                    code="MALFORMED_MAPPING",
                    message=(
                        f"Step '{step.id}': mapping for '{input_field}' has malformed "
                        f"source '{source}' (expected '$steps.<step_id>.<field>')"
                    ),
                    step_id=step.id,
                ))
                continue
            src_step_id, src_field = parts
            if src_step_id not in step_by_id:
                errors.append(ValidationError(
                    code="UNKNOWN_MAPPING_STEP",
                    message=(
                        f"Step '{step.id}': mapping for '{input_field}' references "
                        f"unknown step '{src_step_id}'"
                    ),
                    step_id=step.id,
                ))
                continue
            if src_step_id not in step.depends_on:
                errors.append(ValidationError(
                    code="MAPPING_WITHOUT_DEPENDENCY",
                    message=(
                        f"Step '{step.id}' maps from '{src_step_id}' but doesn't list "
                        f"it in depends_on"
                    ),
                    step_id=step.id,
                ))
            src_agent_id = step_by_id[src_step_id].recommended.agent_id
            src_agent = agent_by_id.get(src_agent_id)
            if src_agent and src_agent.output_schema:
                props = src_agent.output_schema.get("properties") or {}
                if props and src_field not in props:
                    errors.append(ValidationError(
                        code="UNKNOWN_OUTPUT_FIELD",
                        message=(
                            f"Step '{step.id}': source field '{src_field}' not in "
                            f"output_schema of step '{src_step_id}' "
                            f"(agent '{src_agent_id}', available: {sorted(props.keys())})"
                        ),
                        step_id=step.id,
                    ))
    return errors


# ── New checks: required inputs + type compatibility ────────

def _normalize_types(type_spec) -> set[str]:
    """
    JSON Schema's 'type' may be a string or list. Return as a set.
    Empty set means 'no type info' — treat as permissive.
    """
    if isinstance(type_spec, list):
        return {t for t in type_spec if isinstance(t, str)}
    if isinstance(type_spec, str):
        return {type_spec}
    return set()


def _types_compatible(src_types: set[str], tgt_types: set[str]) -> bool:
    """
    Pragmatic JSON Schema type compatibility.

    Returns True when the source value (which can be any of src_types) is
    guaranteed to be acceptable by the target (which accepts tgt_types).

    Rules:
      - missing type info on either side -> permissive (return True)
      - every src type must be acceptable by the target
      - 'integer' is acceptable wherever 'number' is acceptable
      - 'null' on the source requires 'null' on the target
    """
    if not src_types or not tgt_types:
        return True
    for s in src_types:
        if s in tgt_types:
            continue
        if s == "integer" and "number" in tgt_types:
            continue
        return False
    return True


def _check_required_inputs_mapped(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    """Every field listed in target's input_schema.required must have a mapping."""
    errors: list[ValidationError] = []
    agent_by_id: dict[str, AgentCandidate] = {
        c.agent_id: c for cs in candidates.values() for c in cs
    }

    for step in plan.steps:
        agent = agent_by_id.get(step.recommended.agent_id)
        if not agent or not agent.input_schema:
            continue
        required = agent.input_schema.get("required") or []
        if not isinstance(required, list):
            continue
        for field in required:
            if field not in step.input_mapping:
                errors.append(ValidationError(
                    code="REQUIRED_INPUT_NOT_MAPPED",
                    message=(
                        f"Step '{step.id}': required input '{field}' of agent "
                        f"'{step.recommended.agent_id}' has no entry in input_mapping"
                    ),
                    step_id=step.id,
                ))
    return errors


def _check_mapping_types(
    plan: Plan,
    candidates: dict[str, list[AgentCandidate]],
) -> list[ValidationError]:
    """
    For each input_mapping entry, verify the source TYPE is compatible with
    the target field's declared JSON Schema type.

    Three source shapes:
      - "$steps.<id>.<field>"     → look up <field>'s type in <id>'s output_schema
      - "$pipeline_input.<field>" → unknown shape, skip type check
      - any other literal string  → always type 'string'
    """
    errors: list[ValidationError] = []
    agent_by_id: dict[str, AgentCandidate] = {
        c.agent_id: c for cs in candidates.values() for c in cs
    }
    step_by_id = {s.id: s for s in plan.steps}

    for step in plan.steps:
        tgt_agent = agent_by_id.get(step.recommended.agent_id)
        if not tgt_agent or not tgt_agent.input_schema:
            continue
        tgt_props = tgt_agent.input_schema.get("properties") or {}
        if not tgt_props:
            continue

        for input_field, source in step.input_mapping.items():
            tgt_spec = tgt_props.get(input_field)
            if not isinstance(tgt_spec, dict):
                # Target field not declared in schema → can't type-check.
                # Whether to error depends on additionalProperties; staying lenient
                # here keeps backwards compatibility with permissive schemas.
                continue
            tgt_types = _normalize_types(tgt_spec.get("type"))

            if not isinstance(source, str):
                continue

            if source.startswith("$steps."):
                ref = source[len("$steps."):]
                parts = ref.split(".", 1)
                if len(parts) != 2:
                    continue  # already flagged by _check_input_mappings
                src_step_id, src_field = parts
                src_step = step_by_id.get(src_step_id)
                if not src_step:
                    continue
                src_agent = agent_by_id.get(src_step.recommended.agent_id)
                if not src_agent or not src_agent.output_schema:
                    continue
                src_props = src_agent.output_schema.get("properties") or {}
                src_spec = src_props.get(src_field)
                if not isinstance(src_spec, dict):
                    continue
                src_types = _normalize_types(src_spec.get("type"))
                if not _types_compatible(src_types, tgt_types):
                    errors.append(ValidationError(
                        code="TYPE_MISMATCH",
                        message=(
                            f"Step '{step.id}': mapping '{input_field}' = '{source}' — "
                            f"source type {sorted(src_types) or 'unknown'} not "
                            f"compatible with target type {sorted(tgt_types) or 'unknown'}"
                        ),
                        step_id=step.id,
                    ))
            elif source.startswith("$pipeline_input."):
                # Pipeline input shape is unknown at plan time; skip.
                continue
            else:
                # Literal string. Compatible only if target accepts strings.
                if not _types_compatible({"string"}, tgt_types):
                    errors.append(ValidationError(
                        code="LITERAL_TYPE_MISMATCH",
                        message=(
                            f"Step '{step.id}': literal value '{source}' for input "
                            f"'{input_field}' is a string, target expects "
                            f"{sorted(tgt_types) or 'unknown'}"
                        ),
                        step_id=step.id,
                    ))
    return errors
