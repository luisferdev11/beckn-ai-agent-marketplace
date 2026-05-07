"""
Quality Scorer — runs benchmarks against live agents and scores the results.
Scores are stored in memory and updated on demand or on a schedule.
"""

import threading
from datetime import datetime, timezone
from collections import defaultdict
from .benchmarks import BENCHMARKS


_lock          = threading.Lock()
_latest_scores: dict  = {}    # agent_id → latest score run
_score_history: list  = []    # full history of every run


# ── Scoring logic ──────────────────────────────────────────────────────────────

def _score_output(output: str, must_contain: list, must_not_contain: list) -> dict:
    """
    Score a single benchmark result.
    Returns a dict with pass/fail details and a 0.0–1.0 score.
    """
    output_lower = output.lower()

    passed_must     = [kw for kw in must_contain     if kw.lower() in output_lower]
    failed_must     = [kw for kw in must_contain     if kw.lower() not in output_lower]
    failed_must_not = [kw for kw in must_not_contain if kw.lower() in output_lower]

    total_checks = len(must_contain) + len(must_not_contain)
    passed_checks = len(passed_must) + (len(must_not_contain) - len(failed_must_not))

    score = passed_checks / total_checks if total_checks > 0 else 1.0

    return {
        "score":            round(score, 4),
        "passed_keywords":  passed_must,
        "missing_keywords": failed_must,
        "forbidden_found":  failed_must_not,
        "passed":           score == 1.0,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def run_benchmarks(registry: dict) -> dict:
    """
    Run all benchmarks against the live agents in the registry.
    Returns a summary of scores per agent.

    Args:
        registry: the REGISTRY dict from registry.py
    """
    from sla.monitor import check_quality

    run_timestamp = datetime.now(timezone.utc).isoformat()
    results_by_agent: dict = defaultdict(lambda: {"tests": [], "passed": 0, "total": 0})

    for benchmark in BENCHMARKS:
        agent_id  = benchmark["agent_id"]
        task_type = benchmark["task_type"]

        # Skip if agent is not registered
        if agent_id not in registry:
            continue
        if task_type not in registry[agent_id]:
            continue

        agent = registry[agent_id][task_type]

        try:
            output, _ = agent.run(benchmark["payload"])
            scored    = _score_output(
                output,
                benchmark.get("must_contain", []),
                benchmark.get("must_not_contain", []),
            )
            status = "ok"
        except Exception as e:
            output = ""
            scored = {"score": 0.0, "passed": False, "error": str(e)}
            status = "error"

        test_result = {
            "description": benchmark.get("description", ""),
            "task_type":   task_type,
            "status":      status,
            **scored,
        }

        bucket = results_by_agent[agent_id]
        bucket["tests"].append(test_result)
        bucket["total"] += 1
        if scored.get("passed"):
            bucket["passed"] += 1

    # ── Compute final scores per agent ────────────────────────────────────────
    summary = {}
    for agent_id, data in results_by_agent.items():
        total     = data["total"]
        passed    = data["passed"]
        avg_score = (
            sum(t.get("score", 0) for t in data["tests"]) / total
            if total > 0 else 0.0
        )

        agent_summary = {
            "timestamp":   run_timestamp,
            "agent_id":    agent_id,
            "total_tests": total,
            "passed":      passed,
            "failed":      total - passed,
            "score":       round(avg_score, 4),
            "tests":       data["tests"],
        }
        summary[agent_id] = agent_summary

        # Store latest score
        with _lock:
            _latest_scores[agent_id] = agent_summary
            _score_history.append({
                "timestamp": run_timestamp,
                "agent_id":  agent_id,
                "score":     round(avg_score, 4),
            })

        # Check against SLA quality threshold
        # Find first task_type for this agent to pass to check_quality
        first_task = BENCHMARKS[0]["task_type"]
        for b in BENCHMARKS:
            if b["agent_id"] == agent_id:
                first_task = b["task_type"]
                break
        check_quality(agent_id, first_task, avg_score)

    return summary


def get_latest_scores() -> dict:
    """Return the most recent benchmark score for each agent."""
    with _lock:
        return dict(_latest_scores)


def get_score_history(agent_id: str = None) -> list:
    """Return full score history, optionally filtered by agent."""
    with _lock:
        history = list(_score_history)
    if agent_id:
        history = [h for h in history if h["agent_id"] == agent_id]
    return history
