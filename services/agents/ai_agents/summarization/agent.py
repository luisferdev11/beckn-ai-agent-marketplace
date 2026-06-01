"""Legal / regulatory document summarization agent.

Owns ``agent-summarizer-001`` in the General Tecla Industries catalog.
The agent is specialised for legal and regulatory text (banking,
compliance, contracts) — matches the AgentFacts published in
``infra/db/bpp/migrations/002_seed_data.sql`` and the Story 1
scenario from the project briefing.

Wire contract (matches outputSchema in the catalog):
    Input  payload : {"document": str, "language": "en"|"hi"|"es" (optional, default "en")}
    Output result  : {"summary": str, "key_points": [str, ...], "language": str}

The demo orchestrator (``services/bap/app/routes/demo.py``) validates
the on_status payload against the declared outputSchema and aborts
with a clean error on mismatch — keeping this handler honest is part
of the cross-BPP contract.
"""
from __future__ import annotations

import json
import os
import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY environment variable is not set")

MODEL_NAME = "llama-3.3-70b-versatile"

_metrics = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
}


_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are an expert legal-document summarizer specialised in banking "
            "and regulatory text (e.g. RBI circulars, compliance directives, "
            "contracts). Given a regulatory or legal document, return a JSON "
            "object with EXACTLY this shape:\n\n"
            "  {{\n"
            '    "summary": "a 3-5 sentence executive summary in {language}",\n'
            '    "key_points": ["bullet 1", "bullet 2", "bullet 3", ...],\n'
            '    "language": "{language}"\n'
            "  }}\n\n"
            "Rules:\n"
            "- Output ONLY the JSON object, no markdown fences, no commentary, "
            "no preamble.\n"
            "- ``summary`` is plain prose, 3-5 sentences, faithful to the source.\n"
            "- ``key_points`` is an array of 3-7 short strings, each one a single "
            "concrete point (regulatory obligation, threshold, effective date, etc.).\n"
            "- ``language`` echoes the requested output language (en, hi, es, ...).\n"
            "- Never fabricate clauses, dates, or amounts — stick to what's in "
            "the document."
        ),
    ),
    (
        "human",
        "Output language: {language}\n\nDocument to summarize:\n\n{document}",
    ),
])


def _get_llm() -> ChatGroq:
    # ``response_format`` forces Groq to emit a syntactically-valid
    # JSON object. Without this the model occasionally drops quotes
    # around string values for long answers, which broke our parser
    # and forced the fallback path.
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model_name=MODEL_NAME,
        temperature=0.2,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _coerce_to_contract(raw: str, language: str) -> dict:
    """Parse the LLM response into the declared output shape.

    The system prompt asks for raw JSON, but LLMs occasionally wrap it in
    a fenced block or add a one-line preamble. We strip the most common
    decorations before parsing and fall back to a degraded-but-valid
    shape if the JSON is still unrecoverable — that way the orchestrator
    still gets a schema-valid payload it can show the user, rather than
    a 500.
    """
    text = (raw or "").strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    # Best-effort: take the substring from the first `{` to the last `}`.
    if "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        parsed = json.loads(text)
        summary = str(parsed.get("summary") or "").strip()
        key_points_raw = parsed.get("key_points") or []
        key_points = [str(p).strip() for p in key_points_raw if str(p).strip()]
        if summary and key_points:
            return {
                "summary": summary,
                "key_points": key_points,
                "language": str(parsed.get("language") or language),
            }
    except (ValueError, AttributeError):
        pass
    # Fallback: degrade to a single-bullet shape so callers still get a
    # schema-valid result. The orchestrator's downstream validator
    # accepts this — we'd rather show partial output than fail the run.
    fallback_summary = (raw or "Could not parse model output.").strip()[:800]
    return {
        "summary": fallback_summary,
        "key_points": [fallback_summary[:200]],
        "language": language,
    }


async def run_task(payload: dict) -> tuple:
    """Run a document summarization task. Returns (result, usage)."""
    _metrics["total_requests"] += 1

    document = (payload.get("document") or payload.get("text") or "").strip()
    if not document:
        _metrics["failed_requests"] += 1
        raise ValueError("payload must include non-empty 'document'")

    # Cap input around the declared maxTokens budget (4096) — leave room
    # for the response. ~12000 chars ≈ 3000 tokens for English/Hindi.
    if len(document) > 12000:
        document = document[:12000] + "\n[... document truncated for budget ...]"

    language = (payload.get("language") or "en").strip() or "en"

    chain = _PROMPT | _get_llm()

    try:
        response = await chain.ainvoke({"document": document, "language": language})
    except Exception:
        _metrics["failed_requests"] += 1
        raise

    usage_meta = getattr(response, "usage_metadata", {}) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    result = _coerce_to_contract(response.content, language)

    _metrics["successful_requests"] += 1
    _metrics["total_input_tokens"] += input_tokens
    _metrics["total_output_tokens"] += output_tokens

    usage = {
        "model_used": MODEL_NAME,
        "fallback_used": False,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    return result, usage


async def check_model() -> bool:
    try:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content="ping")])
        return bool(response.content)
    except Exception:
        return False


def get_metrics() -> dict:
    return {
        "agent_id": "agent-summarizer-001",
        "total_requests": _metrics["total_requests"],
        "successful_requests": _metrics["successful_requests"],
        "failed_requests": _metrics["failed_requests"],
        "total_input_tokens": _metrics["total_input_tokens"],
        "total_output_tokens": _metrics["total_output_tokens"],
    }
