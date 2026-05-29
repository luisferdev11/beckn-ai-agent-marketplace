"""AgentFacts schema validation for the publish path.

Beckn publish payloads contain a list of catalogs, each with a list of
resources, each with a ``resourceAttributes`` blob — that blob is the
AgentFacts document we own. This module validates each AgentFacts blob
against ``schemas/agentfacts-v1.json`` and returns per-item errors so
the catalog service can decide whether a publish is ACCEPTED, PARTIAL,
or REJECTED.

We deliberately validate inside Python with ``jsonschema`` (Draft 2020-12)
rather than at the SQL layer because per-item error reporting is part of
the on_publish contract.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)


def _resolve_schema_path() -> str:
    """Resolve schema path that works in Docker (/app/) and locally."""
    env = os.getenv("AGENTFACTS_SCHEMA_PATH")
    if env:
        return env
    # In Docker the working dir is /app; locally we walk up from this file
    # until we find schemas/agentfacts-v1.json.
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = here
    for _ in range(10):
        path = os.path.join(candidate, "schemas", "agentfacts-v1.json")
        if os.path.isfile(path):
            return path
        candidate = os.path.dirname(candidate)
    return "/app/schemas/agentfacts-v1.json"


DEFAULT_SCHEMA_PATH = _resolve_schema_path()


@dataclass(frozen=True)
class ItemError:
    """One AgentFacts validation failure, scoped to a single resource."""
    resource_id: str
    code: str
    message: str
    path: str  # JSONPath into resourceAttributes, for debuggability


class AgentFactsValidator:
    """Wraps a jsonschema Draft202012Validator preloaded from disk.

    The schema is loaded once per process. In tests we instantiate with
    an explicit path to keep the suite path-agnostic.
    """

    def __init__(self, schema_path: str = DEFAULT_SCHEMA_PATH):
        self.schema_path = schema_path
        with open(schema_path, "r", encoding="utf-8") as fh:
            self._schema = json.load(fh)
        self._validator = Draft202012Validator(self._schema)

    def validate_one(self, resource_id: str, agent_facts: dict) -> list[ItemError]:
        """Return all validation errors for one AgentFacts blob.

        ``resource_id`` is the Beckn ``resource.id`` (e.g.
        "agent-summarizer-001") — propagated into ItemError so the
        on_publish response can pinpoint which item failed without
        the BPP having to correlate by index.
        """
        if not isinstance(agent_facts, dict):
            return [ItemError(
                resource_id=resource_id,
                code="INVALID_TYPE",
                message="resourceAttributes must be an object",
                path="$",
            )]

        errors: list[ItemError] = []
        for err in self._validator.iter_errors(agent_facts):
            errors.append(ItemError(
                resource_id=resource_id,
                code="SCHEMA_VIOLATION",
                message=err.message,
                path="$." + ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "$",
            ))
        return errors


_default_validator: Optional[AgentFactsValidator] = None


def get_default_validator() -> AgentFactsValidator:
    """Module-level singleton — opens the schema file once."""
    global _default_validator
    if _default_validator is None:
        _default_validator = AgentFactsValidator()
    return _default_validator
