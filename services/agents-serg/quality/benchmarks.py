"""
Quality Benchmarks — test cases with known expected outputs.

Each benchmark has:
  - agent_id:    which agent to test
  - task_type:   which task to call
  - payload:     the input to send
  - must_contain: list of keywords the output MUST include to pass
  - must_not_contain: list of keywords that should NOT appear (optional)
  - description: human-readable label for the test

To add new benchmarks: just append to the BENCHMARKS list.
"""

BENCHMARKS: list[dict] = [

    # ── Summarizer ─────────────────────────────────────────────────────────────
    {
        "agent_id":   "summarizer-v1",
        "task_type":  "summarize",
        "description": "Basic business document summary",
        "payload": {
            "text": (
                "Acme Corp reported record revenue of $4.2 billion in Q3 2024, "
                "a 15% increase compared to Q3 2023. The growth was driven primarily "
                "by the cloud services division, which grew 42%. Net profit reached "
                "$800 million. The CEO announced plans to expand into Asian markets "
                "in 2025 and increase R&D investment by 20%."
            ),
        },
        "must_contain":     ["revenue", "Q3", "cloud", "profit"],
        "must_not_contain": [],
    },
    {
        "agent_id":   "summarizer-v1",
        "task_type":  "summarize",
        "description": "Technical document summary",
        "payload": {
            "text": (
                "The new API version 3.0 introduces breaking changes in authentication. "
                "OAuth2 tokens are now required for all endpoints. The previous API key "
                "method will be deprecated on January 1 2025. Rate limits have been "
                "increased from 100 to 500 requests per minute. Response payloads now "
                "include a new 'metadata' field with timestamps and version info."
            ),
        },
        "must_contain":     ["OAuth2", "deprecated", "rate limit", "metadata"],
        "must_not_contain": [],
    },

    # ── Extractor ──────────────────────────────────────────────────────────────
    {
        "agent_id":   "extractor-v1",
        "task_type":  "extract",
        "description": "Extract contact details",
        "payload": {
            "text":    "Contact Maria Lopez at maria.lopez@company.com or call +34 612 345 678. She is based in Barcelona.",
            "extract": "names, emails, phone numbers, locations",
        },
        "must_contain":     ["Maria Lopez", "maria.lopez@company.com", "Barcelona"],
        "must_not_contain": [],
    },
    {
        "agent_id":   "extractor-v1",
        "task_type":  "extract",
        "description": "Extract financial figures",
        "payload": {
            "text":    "The contract signed on March 5 2024 was worth $250,000. Payment terms are net 30 days.",
            "extract": "dates, amounts, payment terms",
        },
        "must_contain":     ["March", "2024", "250,000"],
        "must_not_contain": [],
    },

    # ── Sentiment ──────────────────────────────────────────────────────────────
    {
        "agent_id":   "sentiment-v1",
        "task_type":  "analyze_sentiment",
        "description": "Clearly negative review",
        "payload": {
            "text": "Terrible service. The product arrived broken and customer support was useless.",
        },
        "must_contain":     ["Negative"],
        "must_not_contain": ["Positive"],
    },
    {
        "agent_id":   "sentiment-v1",
        "task_type":  "analyze_sentiment",
        "description": "Clearly positive review",
        "payload": {
            "text": "Absolutely love this product! Fast delivery, great quality, and excellent support team.",
        },
        "must_contain":     ["Positive"],
        "must_not_contain": ["Negative"],
    },

    # ── Translator ─────────────────────────────────────────────────────────────
    {
        "agent_id":   "translator-v1",
        "task_type":  "translate",
        "description": "Common business phrase translation",
        "payload": {
            "text": "Please find attached the report for your review.",
            "tone": "formal",
        },
        "must_contain":     ["adjunto", "informe"],   # Spanish keywords expected
        "must_not_contain": ["Please", "attached"],   # English should not remain
    },
]
