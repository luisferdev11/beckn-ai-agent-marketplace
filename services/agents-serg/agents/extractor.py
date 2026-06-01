"""
Agent 2 — Structured Data Extractor (Serg Ops)

Extracts structured entities from text. Returns a JSON-formatted string
so the BPP /task envelope (which carries ``result`` as a single string
in the Serg runtime contract) stays unchanged. Consumers parse the
string into a dict before further processing.

The output JSON shape is fixed to a contract the marketplace's demo
orchestrator validates against (declared on the Serg catalog as
``outputSchema.returns = application/json``):

    {
      "organizations": [str, ...],
      "dates": [str, ...],
      "regulatory_references": [str, ...],
      "monetary_amounts": [str, ...],
      "obligations": [str, ...]
    }

Each list can be empty when nothing is found — the keys are always
present so downstream validators can rely on the shape.
"""
from __future__ import annotations

import json
import re

from .base import BaseAgent
from core.llm import call_llm


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


_REQUIRED_KEYS = (
    "organizations",
    "dates",
    "regulatory_references",
    "monetary_amounts",
    "obligations",
)


def _coerce_to_contract(raw: str) -> dict:
    """Parse the LLM output into the declared contract.

    LLMs occasionally wrap JSON in fenced code blocks or add a short
    preamble. We strip the common decorations, then fall back to an
    empty-but-valid shape if parsing fails — better to return zero
    extractions than to break the pipeline.
    """
    text = (raw or "").strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            normalised = {}
            for key in _REQUIRED_KEYS:
                value = parsed.get(key, [])
                if isinstance(value, list):
                    normalised[key] = [str(v).strip() for v in value if str(v).strip()]
                elif value:
                    normalised[key] = [str(value).strip()]
                else:
                    normalised[key] = []
            return normalised
    except (ValueError, AttributeError):
        pass
    return {key: [] for key in _REQUIRED_KEYS}


_SYSTEM_PROMPT = (
    "You are a precision data extractor specialised in legal and regulatory "
    "documents (e.g. RBI circulars, compliance directives, contracts). "
    "Extract structured entities from the text and return ONLY a JSON object "
    "with exactly these keys, each one an array of short strings:\n\n"
    "  {\n"
    '    "organizations":          [...],   // companies, agencies, regulators mentioned\n'
    '    "dates":                  [...],   // effective dates, deadlines, periods\n'
    '    "regulatory_references":  [...],   // section numbers, circulars, laws cited\n'
    '    "monetary_amounts":       [...],   // figures with currency where present\n'
    '    "obligations":            [...]    // concrete actions required\n'
    "  }\n\n"
    "Rules:\n"
    "- Output ONLY the JSON, no fences, no commentary.\n"
    "- Use empty arrays for categories with no findings.\n"
    "- Be faithful to the text — never invent entities."
)


class ExtractorAgent(BaseAgent):

    name      = "extractor-v1"
    task_type = "extract"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - text  (required): text to extract entities from
        """
        text = payload.get("text", "").strip()
        if not text:
            raise ValueError("payload must include 'text'")

        if len(text) > 3000:
            text = text[:3000] + "\n[... trimmed ...]"

        prompt = f"Text to analyse:\n\n{text}\n\nExtract the entities:"

        # json_mode=True forces Groq's response_format=json_object so we
        # never need to recover from unfenced or quoted-key-only output.
        raw, tokens = call_llm(prompt, _SYSTEM_PROMPT, json_mode=True)
        normalised = _coerce_to_contract(raw)
        # Re-emit as compact JSON: the Serg /task contract returns a
        # single string, and downstream parsers expect canonical JSON.
        return json.dumps(normalised, ensure_ascii=False), tokens
