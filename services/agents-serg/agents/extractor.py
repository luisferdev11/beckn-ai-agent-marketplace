"""
Agent 2 — Data Extractor
Extracts structured data (names, dates, emails, numbers) from text.
"""

from .base import BaseAgent
from core.llm import call_llm


class ExtractorAgent(BaseAgent):

    name      = "extractor-v1"
    task_type = "extract"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - text    (required): text to extract from
          - extract (optional): what to look for, e.g. "names, dates, amounts"
                                defaults to common fields if not provided
        """
        text = payload.get("text", "").strip()
        if not text:
            raise ValueError("payload must include 'text'")

        extract_what = payload.get("extract", "names, dates, numbers, locations, emails")

        if len(text) > 3000:
            text = text[:3000] + "\n[... trimmed ...]"

        system = "You are a precise data extraction assistant. Return only what is asked, nothing else."
        prompt = (
            f"Extract the following from the text: {extract_what}\n\n"
            f"Format: one item per line, label each one.\n"
            f"If something is not found, write 'Not found'.\n\n"
            f"Text:\n{text}\n\n"
            f"Extracted data:"
        )

        return call_llm(prompt, system)
