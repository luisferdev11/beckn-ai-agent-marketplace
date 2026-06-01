"""JSON Schema validation between pipeline steps.

Pure module — no I/O, no async. The orchestrator calls
``validate_against`` before sending a select (inbound) and after the
on_status arrives (outbound). Failures carry a stable error code so
the UI can render them next to the offending step in the trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


@dataclass(frozen=True)
class SchemaCheck:
    """Result of validating a payload against a JSON Schema.

    ``ok=True``  → payload matches; ``errors`` is empty.
    ``ok=False`` → payload violates the schema; ``errors`` lists every
                   leaf failure with a JSONPath-ish ``location`` so the
                   UI can highlight the offending field.
    """
    ok: bool
    errors: list[dict[str, str]]


def _format(err: ValidationError) -> dict[str, str]:
    # absolute_path returns a deque of keys/indices; join into "/-style.
    location = "/".join(str(seg) for seg in err.absolute_path) or "(root)"
    return {
        "location": location,
        "message": err.message,
        # validator name (e.g. "required", "type", "minLength") so the UI
        # can group failures by category.
        "rule": str(err.validator or "unknown"),
    }


def validate_against(payload: Any, schema: dict[str, Any]) -> SchemaCheck:
    """Validate ``payload`` against the JSON Schema ``schema``.

    Uses draft-2020-12 (what the AgentFacts contracts target). All
    errors are collected — we do not bail on the first one — so the
    UI can show "summary missing AND key_points wrong type" in one
    pass instead of forcing the caller to re-run.
    """
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.absolute_path)
    if not errors:
        return SchemaCheck(ok=True, errors=[])
    return SchemaCheck(ok=False, errors=[_format(e) for e in errors])
