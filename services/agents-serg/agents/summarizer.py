"""
Agent 1 — Document Summarizer
Summarizes any text document into bullet points.
"""

from .base import BaseAgent
from core.llm import call_llm


class SummarizerAgent(BaseAgent):

    name      = "summarizer-v1"
    task_type = "summarize"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - text       (required): the document content
          - max_points (optional): number of bullet points, default 5
        """
        text = payload.get("text", "").strip()
        if not text:
            raise ValueError("payload must include 'text'")

        max_points = payload.get("max_points", 5)

        # Trim long documents to save tokens
        if len(text) > 3000:
            text = text[:3000] + "\n\n[... document trimmed ...]"

        system = "You are a concise document analyst. Be brief and accurate."
        prompt = (
            f"Summarize the following document in {max_points} bullet points.\n"
            f"Each bullet should be one short sentence.\n\n"
            f"Document:\n{text}\n\n"
            f"Summary:"
        )

        return call_llm(prompt, system)
