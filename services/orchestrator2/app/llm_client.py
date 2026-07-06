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

IMPORTANT: Extra fields beyond those declared in output_schema are ALWAYS \
acceptable. Only reject if REQUIRED fields are missing, have the wrong type, \
or the values are semantically incoherent with the task. Never reject solely \
because the response contains additional fields.

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
        if isinstance(data, dict):
            data_preview = {k: str(v)[:300] for k, v in data.items()}
            data_summary = f"Data fields with previews: {json.dumps(data_preview, ensure_ascii=False)}"
        else:
            data_summary = f"Data: {str(data)[:300]}"

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

    # ── 4. RESHAPE_OUTPUT ────────────────────────────────────────────────

    async def reshape_output(
        self,
        output_schema: dict,
        agent_response: Any,
        step_note: str,
    ) -> dict | None:
        """Ask the LLM to transform an agent's raw response to match the expected outputSchema.

        Used as a last resort when the agent returns valid content but in the
        wrong shape (e.g. {text: "..."} instead of {fields: {}, raw_text: ""}).
        Returns the reshaped dict, or None on failure.
        """
        system = (
            "You are a data transformer. An AI agent produced a valid response but "
            "in a different structure than expected. Your job is to reshape the agent's "
            "response to match the target output_schema.\n\n"
            "Rules:\n"
            "- Extract all relevant information from the agent_response\n"
            "- Map it to the fields defined in output_schema\n"
            "- All required fields in output_schema MUST be present\n"
            "- Preserve the actual content, just restructure it\n"
            "- If the agent returned free text, parse it intelligently to fill structured fields\n"
            "- Return ONLY the reshaped JSON object. No wrapping, no explanation."
        )
        user_msg = json.dumps({
            "output_schema": output_schema,
            "agent_response": agent_response,
            "step_note": step_note,
        }, ensure_ascii=False)

        try:
            result = await self._call(system, user_msg, label="RESHAPE_OUTPUT")
            return result if isinstance(result, dict) else None
        except RuntimeError:
            logger.warning("RESHAPE_OUTPUT LLM call failed")
            return None


    # ── 5. SYNTHESIZE ──────────────────────────────────────────────────

    async def synthesize(
        self,
        goal: str,
        prompt: str,
        raw_result: Any,
    ) -> dict | None:
        """Convert raw structured agent output into a human-readable response.

        Returns {"response": "human readable text"} or None on failure.
        """
        system = (
            "You are the final output formatter for an AI agent pipeline. "
            "The user asked for something and the pipeline produced structured data. "
            "Your job is to present the result as a clear, readable response.\n\n"
            "Rules:\n"
            "- Write a natural, well-formatted response that directly answers what the user asked\n"
            "- Use bullet points, numbered lists, or paragraphs as appropriate\n"
            "- Do NOT show raw JSON, field names, or technical structure\n"
            "- Do NOT mention agents, pipelines, steps, or internal mechanics\n"
            "- Include ALL relevant information from the data — do not omit details\n"
            "- Respond in the same language the user wrote in\n"
            "- Return a JSON object with a single field: {\"response\": \"your formatted text\"}"
        )
        user_msg = json.dumps({
            "user_request": prompt,
            "goal": goal,
            "raw_result": raw_result,
        }, ensure_ascii=False)

        try:
            result = await self._call(system, user_msg, label="SYNTHESIZE")
            if isinstance(result, dict) and "response" in result:
                return result
            return None
        except RuntimeError:
            logger.warning("SYNTHESIZE LLM call failed — returning raw result")
            return None

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
