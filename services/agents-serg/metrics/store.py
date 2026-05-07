import threading
from collections import defaultdict

_lock             = threading.Lock()
_counters: dict   = defaultdict(float)
_histograms: dict = {}
_gauges: dict     = defaultdict(float)

_LATENCY_BUCKETS = [100, 500, 1000, 2500, 5000, 10000, 30000, 60000]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _lk(labels: dict) -> tuple:
    """Convert a labels dict to a sorted tuple (usable as a dict key)."""
    return tuple(sorted(labels.items()))


def _rl(label_tuple: tuple) -> str:
    """Render a label tuple into Prometheus {key="value"} format."""
    if not label_tuple:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in label_tuple) + "}"


# ── Public recording functions ─────────────────────────────────────────────────

def counter_inc(name: str, labels: dict, amount: float = 1.0):
    """Add `amount` to a counter. Counters only go up."""
    with _lock:
        _counters[(name, _lk(labels))] += amount


def gauge_inc(name: str, labels: dict):
    """Add 1 to a gauge (call at task start)."""
    with _lock:
        _gauges[(name, _lk(labels))] += 1


def gauge_dec(name: str, labels: dict):
    """Subtract 1 from a gauge (call at task end)."""
    with _lock:
        _gauges[(name, _lk(labels))] -= 1


def histogram_observe(name: str, labels: dict, value: float):
    """Record a value into histogram buckets (used for latency)."""
    key = (name, _lk(labels))
    with _lock:
        if key not in _histograms:
            _histograms[key] = {
                "sum": 0.0,
                "count": 0,
                "buckets": {b: 0 for b in _LATENCY_BUCKETS},
            }
        h = _histograms[key]
        h["sum"]   += value
        h["count"] += 1
        for b in _LATENCY_BUCKETS:
            if value <= b:
                h["buckets"][b] += 1


# ── Text export (called by GET /metrics) ──────────────────────────────────────

def generate_metrics_text() -> str:
    """Render all stored metrics in Prometheus text exposition format."""
    lines = []

    for metric, help_text in [
        ("agent_transactions_total", "Total agent transactions"),
        ("agent_token_count_total",  "Total tokens consumed"),
    ]:
        lines += [f"# HELP {metric} {help_text}", f"# TYPE {metric} counter"]
        for (n, lbl), val in _counters.items():
            if n == metric:
                lines.append(f"{n}{_rl(lbl)} {val}")

    lines += ["# HELP agent_active_tasks Active tasks right now", "# TYPE agent_active_tasks gauge"]
    for (n, lbl), val in _gauges.items():
        if n == "agent_active_tasks":
            lines.append(f"{n}{_rl(lbl)} {val}")

    lines += ["# HELP agent_latency_ms Latency in milliseconds", "# TYPE agent_latency_ms histogram"]
    for (n, lbl), h in _histograms.items():
        if n == "agent_latency_ms":
            cum = 0
            for b in _LATENCY_BUCKETS:
                cum += h["buckets"][b]
                lines.append(f'{n}_bucket{_rl(_lk(dict(lbl) | {"le": str(b)}))} {cum}')
            lines.append(f'{n}_bucket{_rl(_lk(dict(lbl) | {"le": "+Inf"}))} {h["count"]}')
            lines.append(f'{n}_sum{_rl(lbl)} {h["sum"]}')
            lines.append(f'{n}_count{_rl(lbl)} {h["count"]}')

    return "\n".join(lines) + "\n"
