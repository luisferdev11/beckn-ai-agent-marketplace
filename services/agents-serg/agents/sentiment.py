"""
Agent 6 — Sentiment Analyzer
Detects the emotional tone of any text: positive, negative, or neutral.
Useful for customer feedback, reviews, survey responses, support tickets.
"""

from .base import BaseAgent
from core.llm import call_llm


class SentimentAgent(BaseAgent):

    name      = "sentiment-v1"
    task_type = "analyze_sentiment"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - text   (required): the text to analyze
          - detail (optional): "simple" returns just the label + score,
                               "full" returns label + score + explanation
                               default is "simple"
        """
        text = payload.get("text", "").strip()
        if not text:
            raise ValueError("payload must include 'text'")

        detail = payload.get("detail", "simple")

        if len(text) > 3000:
            text = text[:3000] + "\n[... trimmed ...]"

        system = (
            "You are a sentiment analysis expert. "
            "Be objective and consistent. "
            "Always respond in the exact format requested."
        )

        if detail == "full":
            prompt = (
                f"Analyze the sentiment of the following text.\n\n"
                f"Respond in this exact format:\n"
                f"Sentiment: [Positive / Negative / Neutral / Mixed]\n"
                f"Confidence: [High / Medium / Low]\n"
                f"Score: [number from -1.0 (very negative) to 1.0 (very positive)]\n"
                f"Key signals: [2-3 words or phrases that drove this result]\n"
                f"Explanation: [one sentence explaining why]\n\n"
                f"Text:\n{text}"
            )
        else:
            prompt = (
                f"Analyze the sentiment of the following text.\n\n"
                f"Respond in this exact format:\n"
                f"Sentiment: [Positive / Negative / Neutral / Mixed]\n"
                f"Score: [number from -1.0 (very negative) to 1.0 (very positive)]\n\n"
                f"Text:\n{text}"
            )

        return call_llm(prompt, system)
