"""ORCHESTRATOR-LLM client — wraps Groq API for the 3 orchestration tasks.

Each method: fixed system prompt + user message with data → JSON response.
Retry up to LLM_MAX_RETRIES. On total failure, degrade to deterministic fallback.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from groq import AsyncGroq

from app.config import GROQ_API_KEY, GROQ_MODEL, LLM_MAX_RETRIES, LLM_RETRY_WAIT
from app.shared.validator import validate_against_schema

logger = logging.getLogger(__name__)

# ── System prompts (one per task type) ────────────────────────────────────────

UNDERSTAND_SYSTEM = """\
You are the brain of an AI orchestrator. Your role is to interpret a task \
and produce an execution brief that will guide the orchestration of multiple \
AI agents.

Given:
- goal: the overall objective
- prompt: the user's instruction
- data_summary: a summary of the data to process
- steps: the list of execution steps with their descriptions

Return a JSON object with exactly these fields:
- interpreted_goal: string — what you understand needs to be achieved
- step_notes: object — mapping each stepId to a short, precise instruction \
  describing what that specific step must achieve. Each note should be \
  actionable and focused on the step's role, not the overall goal.

Return ONLY valid JSON. No markdown, no explanation."""

BUILD_PAYLOAD_SYSTEM = """\
You are a payload builder for an AI orchestrator. Your role is to construct \
the optimal input payload for an AI agent.

Given:
- input_schema: the JSON Schema the agent expects
- step_note: what this step must achieve
- interpolated_data: the data already resolved from previous steps
- completed_steps: summary of what agents already returned

Build the payload that should be sent to the agent. The payload MUST conform \
to the input_schema. Use the interpolated_data as the primary source of values. \
Adapt field names and structure to match what the agent expects.

Return ONLY the JSON payload. No wrapping, no explanation."""

VALIDATE_SYSTEM = """\
You are a response validator for an AI orchestrator. Your role is to check \
whether an agent's response meets expectations.

Given:
- output_schema: the JSON Schema the agent should conform to
- agent_payload: the exact payload that was sent to the agent (the task it received)
- agent_response: what the agent actually returned
- step_note: what this step was supposed to achieve
- completed_steps: summary of what agents already returned

Evaluate BOTH:
1. Structure: does the response match the output_schema?
2. Semantics: given the agent_payload (what the agent was asked to do), does \
   the agent_response make sense? The response fields should be interpreted \
   in the context of the task the agent received, not in isolation.

IMPORTANT: Do NOT second-guess the agent's domain logic. If the output \
structure matches the schema and the values are coherent with the task \
described in agent_payload and step_note, mark it as valid.

Return a JSON object with exactly these fields:
- valid: boolean
- reason: string explaining your assessment
- fix_instructions: string with specific instructions to fix the issue \
  (only meaningful when valid=false, set to "" when valid=true)

Return ONLY valid JSON. No markdown, no explanation."""


class GroqClient:
    """Thin async wrapper around Groq API for ORCHESTRATOR-LLM calls."""

    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=GROQ_API_KEY)
        self._model = GROQ_MODEL

    async def _call(self, system: str, user_content: str, label: str = "ORCHESTRATOR-LLM") -> dict:
        """Call Groq with retry. Returns parsed JSON dict."""
        logger.info("[%s] ── REQUEST ──\n  system: %s\n  user: %s",
                     label, system[:120], user_content[:500])

        last_error: Optional[Exception] = None
        for attempt in range(1 + LLM_MAX_RETRIES):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                raw = response.choices[0].message.content
                parsed = json.loads(raw)
                logger.info("[%s] ── RESPONSE ──\n  %s", label, json.dumps(parsed, ensure_ascii=False)[:800])
                return parsed
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "ORCHESTRATOR-LLM call failed (attempt %d/%d): %s",
                    attempt + 1, 1 + LLM_MAX_RETRIES, exc,
                )
                if attempt < LLM_MAX_RETRIES:
                    await asyncio.sleep(LLM_RETRY_WAIT)

        raise RuntimeError(f"ORCHESTRATOR-LLM unavailable after {1 + LLM_MAX_RETRIES} attempts: {last_error}")

    # ── 1. UNDERSTAND_TASK ────────────────────────────────────────────────

    async def understand(
        self,
        goal: str,
        prompt: str,
        data: dict,
        steps: list[dict],
    ) -> dict:
        """Ask the ORCHESTRATOR-LLM to produce an execution_brief."""
        steps_summary = [
            {"id": s["id"], "agent": s["agent"], "rationale": s.get("rationale", "")}
            for s in steps
        ]
        data_keys = list(data.keys()) if isinstance(data, dict) else []
        data_summary = f"Keys: {data_keys}, sample values truncated for brevity."

        user_msg = json.dumps({
            "goal": goal,
            "prompt": prompt,
            "data_summary": data_summary,
            "steps": steps_summary,
        }, ensure_ascii=False)

        try:
            return await self._call(UNDERSTAND_SYSTEM, user_msg, label="UNDERSTAND_TASK")
        except RuntimeError:
            logger.warning("ORCHESTRATOR-LLM failed for UNDERSTAND_TASK — using deterministic fallback")
            return self._fallback_understand(goal, steps)

    @staticmethod
    def _fallback_understand(goal: str, steps: list[dict]) -> dict:
        step_notes = {s["id"]: s.get("rationale", f"Execute {s['agent']}") for s in steps}
        return {"interpreted_goal": goal, "step_notes": step_notes}

    # ── 2. BUILD_PAYLOAD (DEFINE_PROMPT) ──────────────────────────────────

    async def build_payload(
        self,
        input_schema: dict,
        step_note: str,
        interpolated_data: dict,
        completed_steps: dict[str, Any],
        fix_instructions: str = "",
    ) -> dict:
        """Ask the ORCHESTRATOR-LLM to build the agent payload."""
        user_msg = json.dumps({
            "input_schema": input_schema,
            "step_note": step_note,
            "interpolated_data": interpolated_data,
            "completed_steps_summary": self._summarize_steps(completed_steps),
            "fix_instructions": fix_instructions,
        }, ensure_ascii=False)

        try:
            return await self._call(BUILD_PAYLOAD_SYSTEM, user_msg, label="BUILD_PAYLOAD")
        except RuntimeError:
            logger.warning("ORCHESTRATOR-LLM failed for BUILD_PAYLOAD — using interpolated data as-is")
            return interpolated_data

    # ── 3. VALIDATE_RESPONSE ──────────────────────────────────────────────

    async def validate(
        self,
        output_schema: dict,
        agent_payload: dict,
        agent_response: Any,
        step_note: str,
        completed_steps: dict[str, Any],
    ) -> dict:
        """Ask the ORCHESTRATOR-LLM to validate an agent's response."""
        user_msg = json.dumps({
            "output_schema": output_schema,
            "agent_payload": agent_payload,
            "agent_response": agent_response,
            "step_note": step_note,
            "completed_steps_summary": self._summarize_steps(completed_steps),
        }, ensure_ascii=False)

        try:
            result = await self._call(VALIDATE_SYSTEM, user_msg, label="VALIDATE_RESPONSE")
            if "valid" not in result:
                result["valid"] = True
                result["reason"] = "LLM response missing 'valid' field — assuming valid"
                result["fix_instructions"] = ""
            return result
        except RuntimeError:
            logger.warning("ORCHESTRATOR-LLM failed for VALIDATE — falling back to schema-only validation")
            return self._fallback_validate(output_schema, agent_response)

    @staticmethod
    def _fallback_validate(output_schema: dict, agent_response: Any) -> dict:
        """Deterministic fallback: validate structure only with jsonschema."""
        schema = output_schema
        if "examples" in schema and isinstance(schema["examples"], list) and schema["examples"]:
            schema = schema["examples"][0]

        vr = validate_against_schema(agent_response, schema, "OUTPUT")
        if vr.valid:
            return {"valid": True, "reason": "Schema validation passed (deterministic fallback)", "fix_instructions": ""}
        return {
            "valid": False,
            "reason": f"Schema validation failed: {vr.error_message}",
            "fix_instructions": f"Agent response does not match output schema: {vr.error_message}",
        }

    @staticmethod
    def _summarize_steps(completed_steps: dict[str, Any]) -> dict:
        summary = {}
        for step_id, step_data in completed_steps.items():
            if hasattr(step_data, "output"):
                output = step_data.output
                note = step_data.step_note
            elif isinstance(step_data, dict):
                output = step_data.get("output")
                note = step_data.get("step_note", "")
            else:
                output = str(step_data)
                note = ""

            output_preview = str(output)[:200] if output is not None else "null"
            summary[step_id] = {"step_note": note, "output_preview": output_preview}
        return summary
