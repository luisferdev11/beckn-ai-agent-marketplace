"""Synthesise a minimal valid instance from a JSON Schema (Epic E1).

The probe needs a payload that ``jsonschema.validate`` accepts against the
agent's ``inputSchema`` so we can exercise the agent without a human
crafting test data. This is a deliberately small generator — it covers the
JSON-Schema subset agents actually declare (object/array/string/number/
integer/boolean/null, enum, const, default, examples, required) and falls
back to type-appropriate sentinels. It is NOT a general-purpose schema
fuzzer; anything it cannot interpret yields ``None``/empty, which the
validation step then flags.
"""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

_TYPE_SENTINELS: dict[str, Any] = {
    "string": "probe-sample",
    "integer": 1,
    "number": 1.0,
    "boolean": True,
    "null": None,
    "array": [],
    "object": {},
}


def _first_type(schema: dict) -> str | None:
    """Resolve the declared type. JSON Schema allows a list of types; we
    pick the first non-null one (probes want a concrete value)."""
    t = schema.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return (non_null or t)[0] if t else None
    return t


def synthesize(schema: dict) -> Any:
    """Build a value satisfying ``schema``. Honours, in priority order:
    ``default`` → ``const`` → first ``examples`` → ``enum`` → by-type build.
    """
    if not isinstance(schema, dict) or not schema:
        return None

    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    schema_type = _first_type(schema)

    if schema_type == "object" or "properties" in schema:
        return _synth_object(schema)
    if schema_type == "array":
        return _synth_array(schema)
    if schema_type in _TYPE_SENTINELS:
        return _TYPE_SENTINELS[schema_type]

    # Untyped schema: if it has anyOf/oneOf/allOf, try the first branch.
    for combiner in ("anyOf", "oneOf", "allOf"):
        branches = schema.get(combiner)
        if isinstance(branches, list) and branches:
            return synthesize(branches[0])

    return None


def _synth_object(schema: dict) -> dict:
    props: dict = schema.get("properties") or {}
    required = schema.get("required") or list(props.keys())
    out: dict = {}
    for key in required:
        sub = props.get(key)
        out[key] = synthesize(sub) if isinstance(sub, dict) else "probe-sample"
    # Also fill non-required props that declare a default/const/example, so
    # the synthetic payload is as representative as cheaply possible.
    for key, sub in props.items():
        if key in out or not isinstance(sub, dict):
            continue
        if any(k in sub for k in ("default", "const", "examples", "enum")):
            out[key] = synthesize(sub)
    return out


def _synth_array(schema: dict) -> list:
    items = schema.get("items")
    min_items = schema.get("minItems", 0)
    if min_items <= 0:
        return []
    element = synthesize(items) if isinstance(items, dict) else "probe-sample"
    return [element for _ in range(min_items)]


def synthesize_valid_input(input_schema: dict) -> tuple[Any, list[str]]:
    """Synthesise an input and validate it against ``input_schema``.

    Returns ``(payload, errors)`` where ``errors`` is the list of
    jsonschema validation messages (empty when the payload is valid). The
    probe treats a non-empty ``errors`` as ``input_valid=False`` rather
    than crashing — a schema we cannot satisfy is the agent's problem to
    fix, and we record it.
    """
    payload = synthesize(input_schema)
    try:
        validator = Draft202012Validator(input_schema)
        errors = [e.message for e in validator.iter_errors(payload)]
    except Exception as exc:  # noqa: BLE001 — malformed schema itself
        errors = [f"input schema is not a valid JSON Schema: {exc}"]
    return payload, errors


def validate_output(output: Any, output_schema: dict) -> list[str]:
    """Validate an agent's output against its declared ``outputSchema``.
    Returns the list of validation messages (empty == valid)."""
    try:
        validator = Draft202012Validator(output_schema)
        return [e.message for e in validator.iter_errors(output)]
    except Exception as exc:  # noqa: BLE001
        return [f"output schema is not a valid JSON Schema: {exc}"]
