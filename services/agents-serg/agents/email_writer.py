"""
Agent 5 — Email Writer
Drafts a professional email based on a topic and tone.
"""

from .base import BaseAgent
from core.llm import call_llm


class EmailWriterAgent(BaseAgent):

    name      = "email-writer-v1"
    task_type = "write_email"

    def run(self, payload: dict) -> tuple[str, int]:
        """
        payload keys:
          - topic      (required): what the email is about
                                   e.g. "request a meeting with the client"
          - tone       (optional): "formal", "friendly", "urgent" — default "formal"
          - recipient  (optional): who the email is for  e.g. "my manager"
          - context    (optional): any extra background the LLM should know
        """
        topic = payload.get("topic", "").strip()
        if not topic:
            raise ValueError("payload must include 'topic'")

        tone      = payload.get("tone", "formal")
        recipient = payload.get("recipient", "")
        context   = payload.get("context", "")

        recipient_line = f"Recipient: {recipient}\n" if recipient else ""
        context_line   = f"Background context: {context}\n" if context else ""

        system = (
            "You are an expert business communication writer. "
            "Write clear, concise, professional emails. "
            "Return only the email text — subject line first, then the body. "
            "Do not add explanations or comments outside the email."
        )
        prompt = (
            f"Write a {tone} email about the following topic.\n"
            f"{recipient_line}"
            f"{context_line}"
            f"Topic: {topic}\n\n"
            f"Email (subject line + body):"
        )

        return call_llm(prompt, system)
