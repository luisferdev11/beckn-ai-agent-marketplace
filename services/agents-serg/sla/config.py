"""
SLA Configuration — declare the performance promises for each agent.

Each agent has:
  - max_latency_ms:   maximum acceptable response time
  - max_failure_rate: maximum acceptable failure % (0.0 to 1.0)
  - min_quality_score: minimum acceptable quality score (0.0 to 1.0)
                       set to None if quality scoring is not applicable

Severities are assigned automatically by monitor.py based on how badly
the threshold is exceeded.
"""

# SLA definitions per agent_id
SLA_CONFIG: dict[str, dict] = {
    "summarizer-v1": {
        "max_latency_ms":    5000,   # must respond within 5 seconds
        "max_failure_rate":  0.05,   # max 5% failures
        "min_quality_score": 0.70,   # quality benchmark must stay above 70%
    },
    "extractor-v1": {
        "max_latency_ms":    4000,
        "max_failure_rate":  0.05,
        "min_quality_score": 0.75,
    },
    "code-reviewer-v1": {
        "max_latency_ms":    6000,
        "max_failure_rate":  0.05,
        "min_quality_score": 0.65,
    },
    "translator-v1": {
        "max_latency_ms":    4000,
        "max_failure_rate":  0.03,
        "min_quality_score": 0.80,
    },
    "email-writer-v1": {
        "max_latency_ms":    6000,
        "max_failure_rate":  0.05,
        "min_quality_score": 0.65,
    },
    "sentiment-v1": {
        "max_latency_ms":    3000,
        "max_failure_rate":  0.03,
        "min_quality_score": 0.75,
    },
}

# How far over the threshold before severity escalates
# e.g. latency 1.5x the limit = WARNING, 2x = CRITICAL
SEVERITY_THRESHOLDS = {
    "latency": {
        "WARNING":  1.5,   # 1.5x the SLA limit
        "CRITICAL": 2.0,   # 2.0x the SLA limit
    },
    "failure_rate": {
        "WARNING":  1.5,
        "CRITICAL": 3.0,
    },
    "quality": {
        "WARNING":  0.10,  # 10 percentage points below the limit
        "CRITICAL": 0.25,  # 25 percentage points below the limit
    },
}
