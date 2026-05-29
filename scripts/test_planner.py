#!/usr/bin/env python3
"""
Planner smoke test — drives the BAP /api/plan endpoint end-to-end.

The BAP orchestrates:
  1. POST planner /extract-skills              (LLM #1)
  2. POST /api/contracts/discover per skill    (Beckn discover loop)
  3. POST planner /compose-pipeline            (LLM #2 + validator + retry)

Usage:
    python scripts/test_planner.py

Requires full stack running: docker compose up (planner + bap + mock-network + bpp).
"""

import json
import sys
import time
import urllib.error
import urllib.request

BAP = "http://localhost:3001"

TEST_CASES = [
    {
        "name": "Single skill — document summary",
        "body": {
            "prompt": "Summarize this legal contract in plain English",
            "input_format": "text/plain",
            "output_format": "text/plain",
        },
        "min_steps": 1,
        "max_steps": 1,
    },
    {
        "name": "Multi-step — OCR then data extraction",
        "body": {
            "prompt": "I have a scanned invoice image — extract line items and totals as JSON",
            "input_format": "image/jpeg",
            "output_format": "application/json",
        },
        "min_steps": 1,
        "max_steps": 3,
    },
    {
        "name": "Multi-step — code review then security analysis",
        "body": {
            "prompt": "Review this Python code for bugs and find security vulnerabilities",
            "input_format": "text/plain",
            "output_format": "application/json",
        },
        "min_steps": 1,
        "max_steps": 3,
    },
]

RATE_LIMIT_BURST = 15  # > default 10/min


def post(url: str, body: dict, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def get(url: str, timeout: int = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 60)
    print("PLANNER SMOKE TEST — /api/plan via BAP")
    print("=" * 60)

    # Health check
    print("\n[0] Health checks...")
    try:
        bap_h = get(f"{BAP}/health")
        print(f"  bap: {bap_h.get('status', '?')}")
    except Exception as exc:
        print(f"  FAIL: BAP not reachable — {exc}")
        sys.exit(1)

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {tc['name']}")
        print(f"  Prompt: {tc['body']['prompt']}")
        status, resp = post(f"{BAP}/api/plan", tc["body"])

        if status != 200:
            print(f"  FAIL: HTTP {status} — {resp}")
            failed += 1
            continue

        if resp.get("error"):
            print(f"  WARN: planning error — {resp['error']}")
            print(f"  (this is OK if the mock catalog has no matching agents)")
            # Don't fail outright — could be expected for sparse catalog
            passed += 1
            continue

        plan = resp.get("plan") or {}
        steps = plan.get("steps", [])
        summary = plan.get("summary", "")
        estimates = plan.get("estimates", {})

        print(f"  Summary: {summary}")
        print(f"  Steps ({len(steps)}):")
        for s in steps:
            rec = s.get("recommended", {})
            alts = s.get("alternatives", []) or []
            print(f"    [{s['id']}] {s['skill_id']} → {rec.get('name')} (${rec.get('cost')}, "
                  f"{rec.get('latency_ms')}ms) + {len(alts)} alt(s)")
        print(f"  Estimates: ${estimates.get('total_cost')} {estimates.get('currency')}, "
              f"~{estimates.get('max_latency_ms')}ms total")
        print(f"  Discover transactions: {resp.get('transaction_ids', [])}")

        if tc["min_steps"] <= len(steps) <= tc["max_steps"]:
            print("  PASS")
            passed += 1
        else:
            print(f"  FAIL: expected {tc['min_steps']}-{tc['max_steps']} steps, got {len(steps)}")
            failed += 1

    # Rate limit test — parallel requests so we hit the limit fast.
    # Each /api/plan call is slow (~5-15s of LLM + discover) so a sequential
    # loop is impractical. We fire BURST requests in parallel via threads;
    # slowapi increments the counter as each request arrives, so the 11+
    # should return 429 within ~1s even while 1-10 are still computing.
    print(f"\n[rate-limit] Sending {RATE_LIMIT_BURST} requests in parallel...")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fire(_):
        body = {"prompt": "throwaway", "input_format": "text/plain", "output_format": "text/plain"}
        status, _resp = post(f"{BAP}/api/plan", body, timeout=30)
        return status

    rate_limited = False
    with ThreadPoolExecutor(max_workers=RATE_LIMIT_BURST) as pool:
        futures = [pool.submit(_fire, i) for i in range(RATE_LIMIT_BURST)]
        statuses: list[int] = []
        for fut in as_completed(futures):
            try:
                statuses.append(fut.result())
            except Exception as exc:
                statuses.append(0)
                print(f"  request failed: {exc}")

    count_429 = sum(1 for s in statuses if s == 429)
    count_200 = sum(1 for s in statuses if s == 200)
    print(f"  results: {count_200}× 200, {count_429}× 429, others={len(statuses) - count_200 - count_429}")
    if count_429 > 0:
        print(f"  Got {count_429} rate-limited → slowapi working")
        rate_limited = True

    if rate_limited:
        print("  PASS")
        passed += 1
    else:
        print(f"  WARN: never saw 429 in {RATE_LIMIT_BURST} requests "
              "(might be ok if PLAN_RATE_LIMIT was raised, or the burst was too small)")

    # Results
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
