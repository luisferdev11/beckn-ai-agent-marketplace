from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import jsonschema


@dataclass
class ValidationResult:
    valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def validate_against_schema(data: Any, schema: dict, label: str) -> ValidationResult:
    try:
        jsonschema.validate(instance=data, schema=schema)
        return ValidationResult(valid=True)
    except jsonschema.ValidationError as exc:
        return ValidationResult(
            valid=False,
            error_code=f"{label}_SCHEMA_VIOLATION",
            error_message=exc.message,
        )
    except jsonschema.SchemaError as exc:
        return ValidationResult(
            valid=False,
            error_code=f"{label}_SCHEMA_INVALID",
            error_message=f"Schema is malformed: {exc.message}",
        )
