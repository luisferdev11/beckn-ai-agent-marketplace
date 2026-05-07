"""
Agent 4 — Translator (English to Spanish)
Translates any English text into Spanish.
"""

from .base import BaseAgent
from core.llm import call_llm


class TranslatorAgent(BaseAgent):

    name      = "translator-v1"
    task_type = "translate"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - text  (required): English text to translate
          - tone  (optional): "formal" or "informal", default is "formal"
        """
        text = payload.get("text", "").strip()
        if not text:
            raise ValueError("payload must include 'text'")

        tone = payload.get("tone", "formal")

        if len(text) > 3000:
            text = text[:3000] + "\n[... trimmed ...]"

        system = "You are a professional English to Spanish translator. Return only the translated text, no explanations."
        prompt = (
            f"Translate the following English text to Spanish.\n"
            f"Tone: {tone}\n\n"
            f"English text:\n{text}\n\n"
            f"Spanish translation:"
        )

        return call_llm(prompt, system)
