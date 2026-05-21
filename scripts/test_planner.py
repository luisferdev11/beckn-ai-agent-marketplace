#!/usr/bin/env python3
"""
Planner test — sends natural language prompts to POST /plan and prints the plan.

Usage:
    python scripts/test_planner.py

Requires orchestrator running (docker compose up orchestrator).
"""

import json
import sys
import urllib.request
import urllib.error

ORCHESTRATOR = "http://localhost:3003"

TEST_CASES = [
    {
        "name": "Single skill — summarize a document",
        "body": {
            "prompt": "I need to summarize a legal contract",
            "input_format": "application/pdf",
            "output_format": "text/plain",
        },
    },
    {
        "name": "Multi-step — OCR then extract data from invoice",
        "body": {
            "prompt": "I have a scanned invoice image, I need to extract the line items and totals as structured data",
            "input_format": "image/jpeg",
            "output_format": "application/json",
        },
    },
    {
        "name": "Multi-step — translate then sentiment analysis",
        "body": {
            "prompt": "I have customer reviews in Spanish, I need to know the overall sentiment in English",
            "input_format": "text/plain",
            "output_format": "application/json",
        },
    },
]


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": json.loads(e.read().decode())}


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 60)
    print("PLANNER TEST — Orchestrator")
    print("=" * 60)

    # Health check
    print("\n[0] Health check...")
    try:
        h = get(f"{ORCHESTRATOR}/health")
        print(f"  orchestrator: {h.get('status', '?')}")
    except Exception as e:
        print(f"  FAIL: orchestrator not reachable — {e}")
        sys.exit(1)

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {tc['name']}")
        print(f"  Prompt: {tc['body']['prompt']}")
        print(f"  Input:  {tc['body']['input_format']} -> Output: {tc['body']['output_format']}")

        resp = post(f"{ORCHESTRATOR}/plan", tc["body"])

        if "error" in resp:
            print(f"  FAIL: {resp}")
            failed += 1
            continue

        steps = resp.get("steps", [])
        summary = resp.get("summary", "")

        print(f"  Summary: {summary}")
        print(f"  Steps ({len(steps)}):")
        for s in steps:
            print(f"    {s['step']}. [{s['skill_id']}] {s['reason']}")

        if len(steps) > 0:
            print(f"  PASS")
            passed += 1
        else:
            print(f"  FAIL: empty plan")
            failed += 1

    # Results
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {len(TEST_CASES)} total")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
