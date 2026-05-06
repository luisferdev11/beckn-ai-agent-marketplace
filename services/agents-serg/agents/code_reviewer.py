"""
Agent 3 — Code Reviewer
Explains what a piece of code does in plain English.
"""

from .base import BaseAgent
from core.llm import call_llm


class CodeReviewerAgent(BaseAgent):

    name      = "code-reviewer-v1"
    task_type = "review"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - code     (required): the code snippet to explain
          - language (optional): hint like "python" or "javascript"
        """
        code = payload.get("code", "").strip()
        if not code:
            raise ValueError("payload must include 'code'")

        language  = payload.get("language", "")
        lang_hint = f"Language: {language}\n" if language else ""

        if len(code) > 3000:
            code = code[:3000] + "\n# ... trimmed ..."

        system = "You are a senior developer explaining code to a junior developer. Be clear and simple."
        prompt = (
            f"{lang_hint}"
            f"Explain what this code does in plain English.\n"
            f"Cover: purpose, inputs, outputs, key logic.\n"
            f"Keep it under 150 words.\n\n"
            f"Code:\n{code}\n\n"
            f"Explanation:"
        )

        return call_llm(prompt, system)
