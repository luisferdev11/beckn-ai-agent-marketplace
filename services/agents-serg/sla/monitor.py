"""
SLA Monitor — compares actual metrics against declared SLA promises.
Violations are stored in memory and available via GET /sla/violations.
"""

import threading
from datetime import datetime, timezone
from collections import defaultdict
from .config import SLA_CONFIG, SEVERITY_THRESHOLDS


_lock      = threading.Lock()
_violations: list[dict] = []          # all violations ever recorded this session
_failure_counts: dict   = defaultdict(lambda: {"total": 0, "failed": 0})


# ── Internal helpers ───────────────────────────────────────────────────────────

def _latency_severity(actual_ms: float, limit_ms: float) -> str | None:
    ratio = actual_ms / limit_ms
    if ratio >= SEVERITY_THRESHOLDS["latency"]["CRITICAL"]:
        return "CRITICAL"
    if ratio >= SEVERITY_THRESHOLDS["latency"]["WARNING"]:
        return "WARNING"
    return None


def _failure_severity(actual_rate: float, limit_rate: float) -> str | None:
    if limit_rate == 0:
        return "CRITICAL" if actual_rate > 0 else None
    ratio = actual_rate / limit_rate
    if ratio >= SEVERITY_THRESHOLDS["failure_rate"]["CRITICAL"]:
        return "CRITICAL"
    if ratio >= SEVERITY_THRESHOLDS["failure_rate"]["WARNING"]:
        return "WARNING"
    return None


def _quality_severity(actual_score: float, limit_score: float) -> str | None:
    gap = limit_score - actual_score   # how far below the minimum
    if gap >= SEVERITY_THRESHOLDS["quality"]["CRITICAL"]:
        return "CRITICAL"
    if gap >= SEVERITY_THRESHOLDS["quality"]["WARNING"]:
        return "WARNING"
    return None


def _record_violation(agent_id: str, task_type: str, violation_type: str,
                      severity: str, promised, actual, unit: str = ""):
    entry = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "agent_id":       agent_id,
        "task_type":      task_type,
        "violation_type": violation_type,   # "latency" | "failure_rate" | "quality"
        "severity":       severity,          # "WARNING" | "CRITICAL"
        "promised":       promised,
        "actual":         round(actual, 4),
        "unit":           unit,
    }
    with _lock:
        _violations.append(entry)
    return entry


# ── Public API ─────────────────────────────────────────────────────────────────

def check_transaction(agent_id: str, task_type: str,
                      latency_ms: float, status: str) -> list[dict]:
    """
    Called after every agent transaction.
    Checks latency and updates the rolling failure rate.
    Returns a list of any new violations found (empty list = all good).
    """
    sla = SLA_CONFIG.get(agent_id)
    if not sla:
        return []   # no SLA defined for this agent, skip

    new_violations = []
    key = (agent_id, task_type)

    # ── Update failure rate tracking ──────────────────────────────────────────
    with _lock:
        _failure_counts[key]["total"]  += 1
        if status == "failure":
            _failure_counts[key]["failed"] += 1
        total  = _failure_counts[key]["total"]
        failed = _failure_counts[key]["failed"]

    actual_failure_rate = failed / total if total > 0 else 0.0

    # ── Check latency ─────────────────────────────────────────────────────────
    severity = _latency_severity(latency_ms, sla["max_latency_ms"])
    if severity:
        v = _record_violation(
            agent_id, task_type,
            violation_type = "latency",
            severity       = severity,
            promised       = sla["max_latency_ms"],
            actual         = latency_ms,
            unit           = "ms",
        )
        new_violations.append(v)

    # ── Check failure rate (only meaningful after 10+ transactions) ───────────
    if total >= 10:
        severity = _failure_severity(actual_failure_rate, sla["max_failure_rate"])
        if severity:
            v = _record_violation(
                agent_id, task_type,
                violation_type = "failure_rate",
                severity       = severity,
                promised       = sla["max_failure_rate"],
                actual         = actual_failure_rate,
                unit           = "ratio",
            )
            new_violations.append(v)

    return new_violations


def check_quality(agent_id: str, task_type: str, score: float) -> list[dict]:
    """
    Called after a quality benchmark run.
    Checks if the score meets the declared minimum quality SLA.
    """
    sla = SLA_CONFIG.get(agent_id)
    if not sla or sla.get("min_quality_score") is None:
        return []

    new_violations = []
    severity = _quality_severity(score, sla["min_quality_score"])
    if severity:
        v = _record_violation(
            agent_id, task_type,
            violation_type = "quality",
            severity       = severity,
            promised       = sla["min_quality_score"],
            actual         = score,
            unit           = "score 0-1",
        )
        new_violations.append(v)

    return new_violations


def get_violations(agent_id: str = None, severity: str = None) -> list[dict]:
    """Return stored violations, optionally filtered by agent or severity."""
    with _lock:
        results = list(_violations)

    if agent_id:
        results = [v for v in results if v["agent_id"] == agent_id]
    if severity:
        results = [v for v in results if v["severity"] == severity]

    return results


def get_stats() -> dict:
    """Return a summary of current failure rates per agent."""
    with _lock:
        counts = dict(_failure_counts)

    stats = {}
    for (agent_id, task_type), data in counts.items():
        total  = data["total"]
        failed = data["failed"]
        rate   = failed / total if total > 0 else 0.0
        sla    = SLA_CONFIG.get(agent_id, {})
        stats[f"{agent_id}/{task_type}"] = {
            "total_calls":    total,
            "failed_calls":   failed,
            "failure_rate":   round(rate, 4),
            "sla_limit":      sla.get("max_failure_rate", "N/A"),
            "within_sla":     rate <= sla.get("max_failure_rate", 1.0),
        }
    return stats
