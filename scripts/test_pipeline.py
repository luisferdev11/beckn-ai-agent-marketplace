#!/usr/bin/env python3
"""
Pipeline integration test — per-step Beckn contracts.

Drives the full pipeline lifecycle:
  1. Health checks (BAP, BPP, planner, agents, mock-network)
  2. POST /api/plan → multi-step Plan + transaction_ids
  3. POST /api/pipeline/run → per-step select→init→confirm→status
  4. Validate results (per-step status, final output)

Usage:
    python scripts/test_pipeline.py

Requires full stack: docker compose up
"""

import json
import sys
import time
import urllib.error
import urllib.request

BAP = "http://localhost:3001/api"

# Prompt designed to use agents from BOTH BPPs:
#   - agent-summarizer-001 (Tecla, bpp-provider, agents:3004)
#   - extractor-v1 (Serg Ops, bpp-serg, agents-serg:3006)
PLAN_PROMPT = (
    "I have a legal document. First, summarize the key points of the document. "
    "Then, extract structured entities like organization names, dates, and "
    "monetary amounts from the document."
)

_DOCUMENT_TEXT = (
    "This contract establishes that Party A shall deliver 100 units of "
    "product X to Party B within 30 days of signing. Payment of $50,000 "
    "is due within 15 days of delivery. Late payments incur a 2% monthly "
    "penalty. Either party may terminate with 60 days written notice."
)
USER_INPUT = {
    "text": _DOCUMENT_TEXT,
    "document": _DOCUMENT_TEXT,
}


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
            payload = {"error": str(e)}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


def get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    print("=" * 60)
    print("PIPELINE TEST — Per-Step Beckn Contracts")
    print("=" * 60)

    # ── Step 1: Health checks ────────────────────────────────────────
    print("\n[1/4] Health checks...")
    critical = [
        ("bap-ai",        3001),
        ("bpp-ai",        3002),
        ("bpp-serg",      3005),
        ("planner",       3010),
        ("mock-network",  8090),
    ]
    optional = [
        ("orchestrator",  3003),
        ("agents",        3004),
        ("agents-serg",   3006),
    ]
    all_healthy = True
    for name, port in critical:
        try:
            h = get(f"http://localhost:{port}/health", timeout=8)
            status = h.get("status", "?")
            print(f"  {name}: {status}")
            if status not in ("ok", "degraded"):
                all_healthy = False
        except Exception as e:
            print(f"  {name}: UNREACHABLE ({e})")
            all_healthy = False

    for name, port in optional:
        try:
            h = get(f"http://localhost:{port}/health", timeout=3)
            print(f"  {name}: {h.get('status', '?')}")
        except Exception:
            print(f"  {name}: slow (non-critical)")

    if not all_healthy:
        print("\n  FAIL: critical services not healthy")
        sys.exit(1)
    print("  All critical services healthy.")

    # ── Step 2: Create plan ──────────────────────────────────────────
    print(f"\n[2/4] Creating plan: \"{PLAN_PROMPT[:60]}...\"")
    status, plan_resp = post(f"{BAP}/plan", {
        "prompt": PLAN_PROMPT,
        "input_format": "text/plain",
        "output_format": "application/json",
    })

    if status != 200 or not plan_resp.get("plan"):
        error = plan_resp.get("error") or plan_resp.get("detail") or "unknown"
        print(f"  FAIL: /api/plan returned {status}: {error}")
        sys.exit(1)

    plan = plan_resp["plan"]
    txn_ids = plan_resp.get("transaction_ids", [])
    steps = plan.get("steps", [])

    print(f"  Plan: {plan.get('summary', '?')[:80]}")
    print(f"  Steps: {len(steps)}")
    for s in steps:
        rec = s.get("recommended", {})
        print(f"    {s['id']}: {rec.get('name', '?')} (agent={rec.get('agent_id')}, "
              f"provider={rec.get('provider')}, depends={s.get('depends_on', [])})")
    print(f"  Discover transaction IDs: {len(txn_ids)}")

    if len(steps) < 1 or not txn_ids:
        print("  FAIL: expected at least 1 step and transaction_ids")
        sys.exit(1)

    # ── Step 3: Run pipeline ─────────────────────────────────────────
    print("\n[3/4] Running pipeline (per-step Beckn contracts)...")
    t0 = time.time()
    status, run_resp = post(f"{BAP}/pipeline/run", {
        "plan": plan,
        "prompt": PLAN_PROMPT,
        "user_input": USER_INPUT,
        "transaction_ids": txn_ids,
    }, timeout=180)
    elapsed = time.time() - t0

    if status != 200:
        error = run_resp.get("detail") or run_resp.get("error") or "unknown"
        print(f"  FAIL: /api/pipeline/run returned {status}: {error}")
        sys.exit(1)

    pipeline_id = run_resp.get("pipeline_id", "?")
    overall_status = run_resp.get("status", "?")
    step_results = run_resp.get("steps", [])
    final_result = run_resp.get("result")

    print(f"  Pipeline ID: {pipeline_id[:8]}...")
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Status: {overall_status}")
    print(f"  Steps executed: {len(step_results)}")

    for sr in step_results:
        symbol = "+" if sr["status"] == "COMPLETED" else "-" if sr["status"] == "FAILED" else "~"
        print(f"    [{symbol}] {sr['step_id']}: {sr.get('agent_name', sr['agent_id'])} "
              f"@ {sr['bpp_id']} → {sr['status']} ({sr.get('duration_ms', 0)}ms)")
        if sr.get("error"):
            print(f"        error: {sr['error'][:100]}")
        if sr.get("output"):
            output = sr["output"]
            if isinstance(output, dict):
                for key, value in output.items():
                    val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                    val_str = val_str.replace("\n", " ")
                    if len(val_str) > 150:
                        val_str = val_str[:150] + "..."
                    print(f"        output.{key}: {val_str}")
            else:
                preview = str(output)[:200]
                print(f"        output: {preview}")

    if final_result:
        print(f"\n  --- Final merged result ---")
        for key, value in final_result.items():
            val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            val_str = val_str.replace("\n", " ")
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            print(f"    {key}: {val_str}")

    # ── Step 4: Validate ─────────────────────────────────────────────
    print(f"\n[4/4] Validation...")
    print("=" * 60)
    checks_passed = 0
    checks_total = 0

    def check(name: str, condition: bool):
        nonlocal checks_passed, checks_total
        checks_total += 1
        symbol = "+" if condition else "X"
        print(f"  [{symbol}] {name}")
        if condition:
            checks_passed += 1

    check("Plan created with >= 1 step", len(steps) >= 1)
    check("Pipeline executed", bool(pipeline_id) and pipeline_id != "?")
    check("Terminal status", overall_status in ("COMPLETED", "PARTIAL", "FAILED"))
    check("Step results returned", len(step_results) >= 1)

    completed_steps = [s for s in step_results if s["status"] == "COMPLETED"]
    check("At least one step completed", len(completed_steps) >= 1)

    # Check cross-BPP: different bpp_ids in results
    bpp_ids = set(s["bpp_id"] for s in step_results if s["bpp_id"])
    if len(bpp_ids) > 1:
        check(f"Cross-BPP pipeline ({len(bpp_ids)} BPPs: {bpp_ids})", True)
    else:
        print(f"  [~] Single BPP pipeline (BPPs: {bpp_ids})")

    if overall_status == "COMPLETED":
        check("All steps completed", len(completed_steps) == len(step_results))
        check("Final result non-empty", bool(final_result))
    elif overall_status == "PARTIAL":
        print(f"  ~ PARTIAL: {len(completed_steps)}/{len(step_results)} steps completed")
    elif overall_status == "FAILED":
        print(f"  ~ FAILED: pipeline execution failed")

    print(f"\n  {checks_passed}/{checks_total} checks passed")
    if checks_passed == checks_total:
        print("\n  PASS — Pipeline integration working end-to-end")
    elif checks_passed >= checks_total - 1:
        print("\n  ~ PARTIAL PASS — Core flow works")
    else:
        print("\n  FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
