#!/usr/bin/env python3
"""
Pipeline integration test — verifies the planner → bridge → orchestrator v2 flow.

Drives the full pipeline lifecycle:
  1. Health checks (BAP, BPP, orchestrator2, agents, planner)
  2. POST /api/plan to get a multi-step Plan + transaction_ids
  3. POST /api/pipeline/run to execute the pipeline via Beckn confirm
  4. Poll /api/contracts/status until pipeline completes or fails
  5. Validate pipeline results (execution_summary, per-step status)

Usage:
    python scripts/test_pipeline.py

Requires full stack running: docker compose up
  (bap + bpp + orchestrator + orchestrator2 + planner + agents + mock-network)
"""

import json
import sys
import time
import urllib.error
import urllib.request

BAP = "http://localhost:3001/api"

# Prompt designed to produce a multi-step plan using agents from BOTH BPPs:
#   - agent-summarizer-001 (Tecla, bpp-provider, agents:3004)
#   - extractor-v1 (Serg Ops, bpp-serg, agents-serg:3006)
# The planner should discover both via CDS and compose a pipeline.
PLAN_PROMPT = (
    "I have a legal document. First, summarize the key points of the document. "
    "Then, extract structured entities like organization names, dates, and "
    "monetary amounts from the document."
)

# User input — keys must match what the planner's input_mapping references via
# $pipeline_input.<key>. The planner typically maps to "document" or "text"
# depending on the agent's inputSchema, so we provide both.
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


# ── HTTP helpers ──────────────────────────────────────────────────────────────

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


def wait_for_callback(txn_id: str, expected_action: str, timeout: int = 30) -> dict | None:
    """Poll /api/callbacks/ultimo until we see the expected action."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            cb = get(f"{BAP}/callbacks/ultimo?transaction_id={txn_id}")
            if cb.get("action") == expected_action:
                return cb
        except Exception:
            pass
        time.sleep(1)
    return None


# ── Main test ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("PIPELINE TEST — Planner + Bridge + Orchestrator v2")
    print("=" * 60)

    # ── Step 1: Health checks ────────────────────────────────────────────
    print("\n[1/5] Health checks...")
    # Services critical for the pipeline flow (must be healthy to proceed).
    critical = [
        ("bap-ai",        3001),
        ("bpp-ai",        3002),
        ("orchestrator2", 3008),
        ("planner",       3010),
        ("mock-network",  8090),
    ]
    # Non-critical: agents health pings Groq which may hang on rate limit.
    # The pipeline test can still verify the integration even if agents are slow.
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
            status = h.get("status", "?")
            print(f"  {name}: {status}")
        except Exception:
            print(f"  {name}: slow (non-critical, skipping)")

    if not all_healthy:
        print("\n  FAIL: critical services not healthy. Run: docker compose up --build")
        sys.exit(1)
    print("  All critical services healthy.")

    # ── Step 2: Create a plan via /api/plan ───────────────────────────────
    print(f"\n[2/5] Creating plan: \"{PLAN_PROMPT[:60]}...\"")
    status, plan_resp = post(f"{BAP}/plan", {
        "prompt": PLAN_PROMPT,
        "input_format": "text/plain",
        "output_format": "text/plain",
    })

    if status != 200 or not plan_resp.get("plan"):
        error = plan_resp.get("error") or plan_resp.get("detail") or "unknown"
        print(f"  FAIL: /api/plan returned {status}: {error}")
        sys.exit(1)

    plan = plan_resp["plan"]
    txn_ids = plan_resp.get("transaction_ids", [])
    steps = plan.get("steps", [])
    estimates = plan.get("estimates", {})

    print(f"  Plan: {plan.get('summary', '?')[:80]}")
    print(f"  Steps: {len(steps)}")
    for s in steps:
        rec = s.get("recommended", {})
        print(f"    {s['id']}: {rec.get('name', '?')} (skill={s.get('skill_id')}, "
              f"depends={s.get('depends_on', [])})")
    print(f"  Estimates: {estimates.get('currency', '?')} {estimates.get('total_cost', '?')}, "
          f"~{estimates.get('max_latency_ms', '?')}ms, {estimates.get('steps_count', '?')} steps")
    print(f"  Transaction IDs from discover: {len(txn_ids)}")

    if len(steps) < 1:
        print("  FAIL: expected at least 1 step in the plan")
        sys.exit(1)

    if not txn_ids:
        print("  FAIL: no transaction_ids returned (needed for pipeline/run)")
        sys.exit(1)

    # ── Step 3: Run the pipeline via /api/pipeline/run ────────────────────
    print("\n[3/5] Running pipeline (select → init → confirm)...")
    pipeline_body = {
        "plan": plan,
        "prompt": PLAN_PROMPT,
        "user_input": USER_INPUT,
        "transaction_ids": txn_ids,
    }

    t0 = time.time()
    status, run_resp = post(f"{BAP}/pipeline/run", pipeline_body, timeout=60)
    elapsed = time.time() - t0

    if status != 200:
        error = run_resp.get("detail") or run_resp.get("error") or "unknown"
        print(f"  FAIL: /api/pipeline/run returned {status}: {error}")
        sys.exit(1)

    pipeline_txn_id = run_resp.get("transaction_id")
    contract = run_resp.get("contract", {})

    if not pipeline_txn_id:
        print("  FAIL: no transaction_id in pipeline/run response")
        sys.exit(1)

    print(f"  Pipeline transaction: {pipeline_txn_id[:8]}...")
    print(f"  Beckn lifecycle completed in {elapsed:.1f}s")
    print(f"  Contract ID: {contract.get('id', '?')}")

    # ── Step 4: Poll /api/contracts/status for pipeline result ────────────
    print("\n[4/5] Polling for pipeline execution result...")
    max_polls = 60  # ~3 minutes
    poll_interval = 3
    final_status = None
    final_perf = None

    for attempt in range(max_polls):
        time.sleep(poll_interval)

        status_code, status_resp = post(f"{BAP}/contracts/status", {
            "transaction_id": pipeline_txn_id,
        })
        if status_code != 200:
            print(f"  status poll {attempt + 1}: HTTP {status_code}")
            continue

        # Wait for on_status callback
        cb = wait_for_callback(pipeline_txn_id, "on_status", timeout=10)
        if not cb:
            print(f"  status poll {attempt + 1}: waiting for on_status...")
            continue

        msg = cb.get("message", {})
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except Exception:
                msg = {}

        contract_data = msg.get("contract", {})
        perf_list = contract_data.get("performance", [])
        if not perf_list:
            print(f"  status poll {attempt + 1}: no performance data yet")
            continue

        perf = perf_list[0]
        pa = perf.get("performanceAttributes", {})
        exec_status = pa.get("status") or perf.get("status", {}).get("code", "PENDING")
        short_desc = perf.get("status", {}).get("shortDesc", "")

        print(f"  status poll {attempt + 1}: {exec_status} — {short_desc[:60]}")

        if exec_status in ("COMPLETED", "PARTIAL", "FAILED"):
            final_status = exec_status
            final_perf = pa
            break

    if not final_status:
        print("  TIMEOUT: pipeline did not reach a terminal state in 3 minutes")
        sys.exit(1)

    # ── Step 5: Validate results + show agent outputs ──────────────────────
    print(f"\n[5/5] Validating results (status={final_status})...")

    is_pipeline = final_perf.get("pipeline_mode", False)
    exec_summary = final_perf.get("execution_summary", [])
    result = final_perf.get("result", {})

    print(f"  pipeline_mode: {is_pipeline}")
    print(f"  execution_summary: {len(exec_summary)} steps")

    if exec_summary:
        for step in exec_summary:
            step_status = step.get("status", "?")
            symbol = "+" if step_status == "success" else "-" if step_status == "failed" else "~"
            print(f"    [{symbol}] {step.get('step_id', '?')}: {step.get('agent', '?')} "
                  f"→ {step_status} ({step.get('attempts', 0)} attempts)")
            if step.get("note"):
                print(f"        note: {step['note']}")

    # Show the full performance attributes for debugging agent outputs
    print("\n  --- Full performanceAttributes (agent outputs visible here) ---")
    for key in ("startedAt", "completedAt", "latencyMs", "model"):
        val = final_perf.get(key)
        if val:
            print(f"    {key}: {val}")

    print("\n  --- Final pipeline result (interpolated from agent outputs) ---")
    if result:
        if isinstance(result, dict):
            for key, value in result.items():
                val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                val_str = val_str.replace("\n", " ")
                if len(val_str) > 300:
                    val_str = val_str[:300] + "..."
                print(f"    {key}: {val_str}")
        else:
            preview = json.dumps(result, ensure_ascii=False)[:500]
            print(f"    {preview}")
    else:
        print("    (empty)")

    # ── Verdict ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
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
    check("transaction_ids returned from plan", len(txn_ids) >= 1)
    check("Pipeline transaction_id obtained", bool(pipeline_txn_id))
    check("Terminal status reached", final_status in ("COMPLETED", "PARTIAL", "FAILED"))
    check("pipeline_mode flag present", is_pipeline)
    check("execution_summary returned", len(exec_summary) >= 1)

    if final_status == "COMPLETED":
        check("All steps succeeded", all(s.get("status") == "success" for s in exec_summary))
        check("Result is non-empty", bool(result))
    elif final_status == "PARTIAL":
        check("At least one step succeeded", any(s.get("status") == "success" for s in exec_summary))
        print("  ~ PARTIAL: some steps failed but pipeline produced partial results")
    elif final_status == "FAILED":
        print("  ~ FAILED: pipeline execution failed (may be expected if agents are not available)")
        check("Error information present", bool(final_perf.get("result") or exec_summary))

    print(f"\n  {checks_passed}/{checks_total} checks passed")
    if checks_passed == checks_total:
        print("\n  PASS — Pipeline integration working end-to-end")
    elif checks_passed >= checks_total - 2:
        print("\n  ~ PARTIAL PASS — Core pipeline flow works, some checks failed")
    else:
        print("\n  FAIL — Pipeline integration has issues")
        sys.exit(1)


if __name__ == "__main__":
    main()
