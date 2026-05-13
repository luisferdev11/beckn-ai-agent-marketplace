"""
Agent Registry — the only file you need to edit when adding a new agent.

Steps to add a new agent:
  1. Create agents/your_agent.py  (copy any existing agent as a template)
  2. Import it here
  3. Add it to REGISTRY below
  That's it — the API picks it up automatically.
"""

from agents.summarizer    import SummarizerAgent
from agents.extractor     import ExtractorAgent
from agents.code_reviewer import CodeReviewerAgent
from agents.translator    import TranslatorAgent
from agents.email_writer  import EmailWriterAgent
from agents.sentiment     import SentimentAgent

# ── Add new agent imports here ─────────────────────────────────────────────────
# from agents.translator  import TranslatorAgent
# from agents.classifier  import ClassifierAgent


# ── Registry: agent_id → { task_type → agent instance } ──────────────────────
# Each agent instance is created once at startup and reused for all requests.

REGISTRY: dict[str, dict[str, object]] = {
    "summarizer-v1": {
        "summarize": SummarizerAgent(),
    },
    "extractor-v1": {
        "extract": ExtractorAgent(),
    },
    "code-reviewer-v1": {
        "review": CodeReviewerAgent(),
    },
    "translator-v1": {                                    # ← add this
        "translate": TranslatorAgent(),
    },
    "email-writer-v1": {
        "write_email": EmailWriterAgent(),
    },
    "sentiment-v1": {
        "analyze_sentiment": SentimentAgent(),
    },
    # ── Add new agents here ────────────────────────────────────────────────────
    # "translator-v1": {
    #     "translate": TranslatorAgent(),
    # },
}
