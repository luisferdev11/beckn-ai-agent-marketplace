"""Invoice / financial document data extraction agent.

Owns ``agent-data-extractor-001`` in the BPP catalog.

Wire contract (matches outputSchema in 002_seed_data.sql):
    Input  : {"document": str, "format": str (optional)}
    Output : {"fields": dict, "raw_text": str}

``fields`` is a flat dict of whatever structured data the LLM can extract
from the document (invoice_number, date, vendor, total, line_items, etc.).
``raw_text`` echoes the original input so downstream steps can pass it to
a summarizer without re-reading the document.
"""
from __future__ import annotations

import json
import os
import re

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY environment variable is not set")

MODEL_NAME = "llama-3.3-70b-versatile"

_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a data extraction specialist. Given a document, extract all "
            "structured information into a flat JSON object.\n\n"
            "Return a JSON object with EXACTLY this shape:\n\n"
            "  {{\n"
            '    "fields": {{\n'
            '      "key": "value",\n'
            '      ...\n'
            "    }},\n"
            '    "raw_text": "the original document text verbatim"\n'
            "  }}\n\n"
            "Rules:\n"
            "- ``fields`` must be a flat object. Extract any structured data present: "
            "dates, amounts, names, IDs, addresses, line items (as a string), totals, etc.\n"
            "- Use snake_case keys (e.g. invoice_number, vendor_name, total_amount).\n"
            "- ``raw_text`` must be the exact input document text, unchanged.\n"
            "- Output ONLY the JSON object. No markdown fences, no commentary."
        ),
    ),
    ("human", "Document to extract from:\n\n{document}"),
])

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model_name=MODEL_NAME,
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _coerce_to_contract(raw: str, document: str) -> dict:
    """Parse LLM response into the declared output shape.

    Falls back to {"fields": {}, "raw_text": document} rather than raising,
    so the orchestrator always receives a schema-valid payload.
    """
    text = (raw or "").strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    if "{" in text and "}" in text:
        text = text[text.index("{"):text.rindex("}") + 1]
    try:
        parsed = json.loads(text)
        fields = parsed.get("fields")
        if isinstance(fields, dict):
            return {
                "fields": fields,
                "raw_text": str(parsed.get("raw_text") or document),
            }
    except (ValueError, AttributeError):
        pass
    return {"fields": {}, "raw_text": document}


async def run_task(payload: dict) -> tuple:
    """Run a data extraction task. Returns (result, usage)."""
    document = (
        payload.get("document")
        or payload.get("text")
        or payload.get("prompt")
        or ""
    ).strip()

    if not document:
        raise ValueError("payload must include non-empty 'document'")

    if len(document) > 12000:
        document = document[:12000] + "\n[... document truncated ...]"

    chain = _PROMPT | _get_llm()
    response = await chain.ainvoke({"document": document})

    usage_meta = getattr(response, "usage_metadata", {}) or {}
    result = _coerce_to_contract(response.content, document)
    usage = {
        "model_used": MODEL_NAME,
        "fallback_used": False,
        "input_tokens": usage_meta.get("input_tokens", 0),
        "output_tokens": usage_meta.get("output_tokens", 0),
    }
    return result, usage
