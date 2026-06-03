#!/usr/bin/env python3
"""
Agent health & functional test — calls every registered agent directly
to verify which ones work and which don't.

Tests both agent services:
  - agents       (port 3004): summarizer, code-reviewer, data-extractor
  - agents-serg  (port 3006): summarizer-v1, extractor-v1, code-reviewer-v1,
                               translator-v1, email-writer-v1, sentiment-v1

Usage:
    python scripts/test_agents.py

Requires: docker compose up
"""

import json
import sys
import time
import urllib.error
import urllib.request


# ── Agent definitions ─────────────────────────────────────────────────────────

AGENTS = [
    # ── agents service (port 3004) ──
    {
        "name": "Legal Document Summarizer",
        "service": "agents",
        "url": "http://localhost:3004/task?agent_id=agent-summarizer-001",
        "payload": {
            "document": "This agreement between Party A and Party B establishes "
                        "that Party A shall deliver 100 units at $500 each within "
                        "30 days. Late delivery incurs a 5% penalty per week.",
        },
        "expect_keys": ["summary"],
    },
    {
        "name": "Code Review Assistant",
        "service": "agents",
        "url": "http://localhost:3004/task?agent_id=agent-code-reviewer-001",
        "payload": {
            "code": "def divide(a, b):\n    return a / b",
            "language": "python",
        },
        "expect_keys": ["review"],
    },
    {
        "name": "Invoice Data Extractor",
        "service": "agents",
        "url": "http://localhost:3004/task?agent_id=agent-data-extractor-001",
        "payload": {
            "document": "Invoice #5678\nDate: 2026-03-01\nFrom: TechCorp\n"
                        "To: RetailCo\nItem: Server Rack x2 @ $3000 = $6000\n"
                        "Tax: $480\nTotal: $6480",
        },
        "expect_keys": ["fields", "raw_text"],
        "note": "May fall back to code-review handler if not properly routed",
    },

    # ── agents-serg service (port 3006) ──
    {
        "name": "Summarizer (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=summarizer-v1",
        "payload": {
            "text": "The European Union has introduced new regulations on AI "
                    "transparency requiring all AI systems to disclose their "
                    "training data sources and model architecture by 2027.",
        },
        "expect_keys": ["summary"],
    },
    {
        "name": "Data Extractor (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=extractor-v1",
        "payload": {
            "text": "Contract between Acme Corp and Widget Inc dated 2026-01-15. "
                    "Acme agrees to pay $50,000 for consulting services. "
                    "Payment due within 30 days of completion.",
        },
        "expect_keys": ["organizations", "dates", "monetary_amounts"],
    },
    {
        "name": "Code Reviewer (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=code-reviewer-v1",
        "payload": {
            "text": "def fibonacci(n):\n    if n <= 1: return n\n    "
                    "return fibonacci(n-1) + fibonacci(n-2)",
        },
        "expect_keys": [],
    },
    {
        "name": "Translator (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=translator-v1",
        "payload": {
            "text": "The quick brown fox jumps over the lazy dog.",
            "target_language": "es",
        },
        "expect_keys": [],
    },
    {
        "name": "Email Writer (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=email-writer-v1",
        "payload": {
            "text": "Write a professional email declining a meeting invitation "
                    "due to scheduling conflict.",
        },
        "expect_keys": [],
    },
    {
        "name": "Sentiment Analyzer (Serg)",
        "service": "agents-serg",
        "url": "http://localhost:3006/task?agent_id=sentiment-v1",
        "payload": {
            "text": "The product arrived broken and customer support was unhelpful. "
                    "Worst experience ever.",
        },
        "expect_keys": [],
    },
]


# ── HTTP helper ───────────────────────────────────────────────────────────────

def post(url: str, body: dict, timeout: int = 30) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {"error": str(e)}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


def get(url: str, timeout: int = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def truncate(s: str, max_len: int = 200) -> str:
    s = s.replace("\n", " ").strip()
    return s[:max_len] + "..." if len(s) > max_len else s


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("AGENT TEST — Direct functional test of all registered agents")
    print("=" * 64)

    # ── Health checks ─────────────────────────────────────────────────────
    print("\n[0] Service health checks...")
    services = {"agents": 3004, "agents-serg": 3006}
    for name, port in services.items():
        try:
            h = get(f"http://localhost:{port}/health")
            status = h.get("status", "?")
            print(f"  {name} (:{port}): {status}")
            if status not in ("ok", "degraded"):
                print(f"    WARN: {name} not fully healthy")
        except Exception as e:
            print(f"  {name} (:{port}): UNREACHABLE — {e}")
            print(f"    Agents on this service will be skipped.")

    # ── Test each agent ───────────────────────────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"Testing {len(AGENTS)} agents...\n")

    results = []
    for i, agent in enumerate(AGENTS, 1):
        name = agent["name"]
        service = agent["service"]
        url = agent["url"]
        payload = agent["payload"]
        expect_keys = agent.get("expect_keys", [])
        note = agent.get("note")

        print(f"[{i}/{len(AGENTS)}] {name} ({service})")
        if note:
            print(f"  note: {note}")

        t0 = time.time()
        status_code, resp = post(url, payload)
        elapsed_ms = int((time.time() - t0) * 1000)

        agent_status = resp.get("status", "?")
        result = resp.get("result")
        error = resp.get("error")
        usage = resp.get("usage", {})
        model = usage.get("model_used", "?")
        latency = usage.get("latency_ms", elapsed_ms)

        verdict = "UNKNOWN"
        if status_code == 0:
            verdict = "UNREACHABLE"
            print(f"  HTTP: UNREACHABLE")
            print(f"  error: {resp.get('error', '?')}")
        elif status_code != 200:
            verdict = "HTTP_ERROR"
            print(f"  HTTP: {status_code}")
            print(f"  error: {json.dumps(resp)[:200]}")
        elif agent_status == "error":
            verdict = "AGENT_ERROR"
            err_msg = error
            if isinstance(error, dict):
                err_msg = error.get("message", str(error))
            print(f"  status: error")
            print(f"  error: {err_msg}")
            print(f"  model: {model}, latency: {latency}ms")
        elif agent_status == "success" and result is not None:
            # Parse result if it's a JSON string
            parsed_result = result
            if isinstance(result, str):
                try:
                    parsed_result = json.loads(result)
                except Exception:
                    parsed_result = result

            # Check expected keys
            missing_keys = []
            if expect_keys and isinstance(parsed_result, dict):
                missing_keys = [k for k in expect_keys if k not in parsed_result]

            if missing_keys:
                verdict = "WRONG_OUTPUT"
                print(f"  status: success BUT missing expected keys: {missing_keys}")
                print(f"  got keys: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else type(parsed_result).__name__}")
            else:
                verdict = "OK"

            print(f"  status: success")
            print(f"  model: {model}, latency: {latency}ms")

            # Show output
            if isinstance(parsed_result, dict):
                for key, value in parsed_result.items():
                    val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                    print(f"  output.{key}: {truncate(val_str)}")
            elif isinstance(parsed_result, str):
                print(f"  output: {truncate(parsed_result)}")
            else:
                print(f"  output: {truncate(str(parsed_result))}")
        else:
            verdict = "UNEXPECTED"
            print(f"  status: {agent_status}")
            print(f"  response: {json.dumps(resp)[:200]}")

        results.append({"name": name, "service": service, "verdict": verdict, "latency": latency})
        print()

    # ── Summary ───────────────────────────────────────────────────────────
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)

    ok = [r for r in results if r["verdict"] == "OK"]
    wrong = [r for r in results if r["verdict"] == "WRONG_OUTPUT"]
    errors = [r for r in results if r["verdict"] in ("AGENT_ERROR", "HTTP_ERROR", "UNREACHABLE", "UNEXPECTED")]

    print(f"\n  {'Agent':<30} {'Service':<14} {'Status':<14} {'Latency':>8}")
    print(f"  {'─' * 30} {'─' * 14} {'─' * 14} {'─' * 8}")
    for r in results:
        symbol = {"OK": "+", "WRONG_OUTPUT": "~", "AGENT_ERROR": "X", "HTTP_ERROR": "X",
                  "UNREACHABLE": "!", "UNEXPECTED": "?"}.get(r["verdict"], "?")
        print(f"  [{symbol}] {r['name']:<27} {r['service']:<14} {r['verdict']:<14} {r['latency']:>6}ms")

    print(f"\n  OK: {len(ok)}  |  Wrong output: {len(wrong)}  |  Errors: {len(errors)}  |  Total: {len(results)}")

    if len(ok) == len(results):
        print("\n  PASS — All agents functional")
    elif len(ok) + len(wrong) >= len(results) // 2:
        print(f"\n  ~ PARTIAL — {len(ok)}/{len(results)} agents fully working")
    else:
        print(f"\n  FAIL — Only {len(ok)}/{len(results)} agents working")
        sys.exit(1)


if __name__ == "__main__":
    main()
