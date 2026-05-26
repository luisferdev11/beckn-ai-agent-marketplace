"""Resolve ${stepN.field} and ${input.field} expressions in plan data."""
from __future__ import annotations

import re
from typing import Any

_EXPR_RE = re.compile(r"^\$\{(.+)\}$")
_INLINE_RE = re.compile(r"\$\{(.+?)\}")


def _resolve_path(path: str, completed_steps: dict, data: dict) -> Any:
    """Resolve a dotted path like 'step1.translation' or 'input.review'."""
    parts = path.split(".", 1)
    if len(parts) < 2:
        return f"${{{path}}}"

    source, field = parts

    if source == "input":
        return data.get(field, f"${{{path}}}")

    step_data = completed_steps.get(source)
    if step_data is None:
        return f"${{{path}}}"

    output = step_data.output if hasattr(step_data, "output") else step_data.get("output")
    if isinstance(output, dict):
        return output.get(field, f"${{{path}}}")

    return f"${{{path}}}"


def interpolate(value: Any, completed_steps: dict, data: dict) -> Any:
    """Recursively resolve ${} expressions in a value.

    - If the entire value is a single expression like "${step1.translation}",
      it is replaced by the resolved value (preserving type: str, list, dict, etc.)
    - If the value is a string with inline expressions, they are string-interpolated.
    - Dicts and lists are traversed recursively.
    - Non-string primitives (int, float, bool, None) pass through unchanged.
    """
    if isinstance(value, str):
        exact = _EXPR_RE.match(value)
        if exact:
            return _resolve_path(exact.group(1), completed_steps, data)

        def _replace(m: re.Match) -> str:
            resolved = _resolve_path(m.group(1), completed_steps, data)
            return str(resolved)

        return _INLINE_RE.sub(_replace, value)

    if isinstance(value, dict):
        return {k: interpolate(v, completed_steps, data) for k, v in value.items()}

    if isinstance(value, list):
        return [interpolate(item, completed_steps, data) for item in value]

    return value
