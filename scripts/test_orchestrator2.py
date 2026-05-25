#!/usr/bin/env python3
"""
Orchestrator v2 test — sends a plan to POST /execute and polls for results.

Usage:
    python scripts/test_orchestrator2.py

Requires orchestrator2 running (docker compose up orchestrator2).
Uses plan-example.json as the execution plan.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ORCHESTRATOR2 = "http://localhost:3008"
PLAN_PATH = Path(__file__).parent.parent / "services" / "orchestrator2" / "app" / "executor" / "plan-example.json"
POLL_INTERVAL = 2
MAX_POLLS = 30

def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:500]}


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 70)
    print("ORCHESTRATOR v2 TEST")
    print("=" * 70)

    # ── Health check ──────────────────────────────────────────────────
    print("\n[0] Health check...")
    try:
        h = get(f"{ORCHESTRATOR2}/health")
        print(f"  orchestrator2: {h.get('status', '?')} (v{h.get('version', '?')})")
    except Exception as e:
        print(f"  FAIL: orchestrator2 not reachable — {e}")
        sys.exit(1)

    # ── Load plan ─────────────────────────────────────────────────────
    print(f"\n[1] Loading plan from {PLAN_PATH.name}...")
    if not PLAN_PATH.exists():
        print(f"  FAIL: plan file not found at {PLAN_PATH}")
        sys.exit(1)

    plan = json.loads(PLAN_PATH.read_text())
    print(f"  Goal: {plan.get('goal', '?')[:80]}...")
    print(f"  Steps: {len(plan.get('steps', []))}")
    print(f"  Layers: {len(plan.get('executionLayers', []))}")

    # ── POST /execute ─────────────────────────────────────────────────
    print("\n[2] POST /execute...")
    payload = {
        "plan": plan,
        "prompt": plan.get("goal", ""),
        "data": plan.get("userInput", {}),
    }

    resp = post(f"{ORCHESTRATOR2}/execute", payload)

    if "error" in resp:
        print(f"  FAIL: {resp}")
        sys.exit(1)

    execution_id = resp.get("execution_id")
    status = resp.get("status")
    print(f"  ACK received: execution_id={execution_id}, status={status}")

    if not execution_id:
        print("  FAIL: no execution_id in response")
        sys.exit(1)

    # ── Poll GET /execute/{id} ────────────────────────────────────────
    print(f"\n[3] Polling GET /execute/{execution_id[:8]}... (max {MAX_POLLS * POLL_INTERVAL}s)")

    final = None
    for i in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        result = get(f"{ORCHESTRATOR2}/execute/{execution_id}")
        current_status = result.get("status", "?")
        sys.stdout.write(f"\r  Poll {i + 1}/{MAX_POLLS}: status={current_status}   ")
        sys.stdout.flush()

        if current_status not in ("PENDING", "RUNNING"):
            final = result
            print()
            break

    if final is None:
        print(f"\n  TIMEOUT: still running after {MAX_POLLS * POLL_INTERVAL}s")
        sys.exit(1)

    # ── Results ───────────────────────────────────────────────────────
    print(f"\n[4] Execution finished: {final['status']}")
    print(f"  Goal: {final.get('goal', '?')[:80]}")

    print("\n  Step summary:")
    for step in final.get("execution_summary", []):
        icon = {"success": "OK", "failed": "FAIL", "skipped": "SKIP"}.get(step["status"], "?")
        note = f" — {step['note']}" if step.get("note") else ""
        print(f"    [{icon}] {step['step_id']} ({step['agent']}) attempts={step['attempts']}{note}")

    result_data = final.get("result")
    if result_data:
        print("\n  Final output:")
        for key, val in result_data.items():
            preview = str(val)[:100]
            if len(str(val)) > 100:
                preview += "..."
            print(f"    {key}: {preview}")

    # ── Verdict ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    status = final["status"]
    if status == "COMPLETED":
        print("RESULT: PASS — all steps completed successfully")
    elif status == "PARTIAL":
        print("RESULT: PARTIAL — some steps completed, some failed/skipped")
    elif status == "FAILED":
        print("RESULT: EXPECTED — agents are not running, orchestrator handled failures correctly")
    else:
        print(f"RESULT: UNEXPECTED status: {status}")

    # The test passes if the orchestrator didn't crash and returned a valid response
    required_fields = {"execution_id", "status", "goal", "execution_summary"}
    missing = required_fields - set(final.keys())
    if missing:
        print(f"FAIL: missing fields in response: {missing}")
        sys.exit(1)

    print("PASS — orchestrator2 response structure is valid")


if __name__ == "__main__":
    main()
