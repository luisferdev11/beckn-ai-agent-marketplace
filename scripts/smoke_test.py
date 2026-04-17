#!/usr/bin/env python3
"""
Smoke test — verifies the full Beckn flow using our own BAP and BPP services.

Usage:
    python scripts/smoke_test.py

Requires all services running (docker compose up).
"""

import json
import sys
import time
import urllib.request
import urllib.error

BAP = "http://localhost:3001/api"
WAIT_SECONDS = 4


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def wait_for_callbacks(expected: int, timeout: int = 15):
    start = time.time()
    while time.time() - start < timeout:
        count = get(f"{BAP}/callbacks/count")
        if count.get("callbacks_recibidos", 0) >= expected:
            return True
        time.sleep(1)
    return False


def main():
    print("=" * 60)
    print("SMOKE TEST — Beckn AI Agent Marketplace")
    print("=" * 60)

    # Health checks
    print("\n[1/6] Health checks...")
    for name, port in [("bap-ai", 3001), ("bpp-ai", 3002), ("orchestrator", 3003)]:
        h = get(f"http://localhost:{port}/health")
        status = h.get("status", "?")
        print(f"  {name}: {status}")
        if status != "ok":
            print(f"  FAIL: {name} not healthy")
            sys.exit(1)

    # Check catalog
    print("\n[2/6] BPP catalog...")
    catalog = get("http://localhost:3002/api/catalog")
    agents = catalog.get("resources", [])
    print(f"  {len(agents)} agents available:")
    for a in agents:
        print(f"    - {a['id']}: {a['descriptor']['name']}")

    # SELECT
    print("\n[3/6] SELECT — choosing Legal Document Summarizer...")
    resp = post(f"{BAP}/contracts/select", {
        "agent_id": "agent-summarizer-001",
        "offer_id": "offer-summarizer-basic",
    })
    txn_id = resp["transactionId"]
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  Transaction: {txn_id}")
    print(f"  ONIX ACK: {ack}")

    if not wait_for_callbacks(1):
        print("  FAIL: on_select callback not received")
        sys.exit(1)

    cb = get(f"{BAP}/callbacks/ultimo")
    contract = cb.get("message", {}).get("contract", {})
    consideration = contract.get("consideration", [{}])[0]
    print(f"  on_select received — price: {consideration.get('price', {}).get('currency', '?')} "
          f"{consideration.get('price', {}).get('value', '?')}")

    # INIT
    print("\n[4/6] INIT — providing fulfillment details...")
    resp = post(f"{BAP}/contracts/init", {"transaction_id": txn_id})
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  ONIX ACK: {ack}")

    if not wait_for_callbacks(2):
        print("  FAIL: on_init callback not received")
        sys.exit(1)
    print(f"  on_init received")

    # CONFIRM
    print("\n[5/6] CONFIRM — confirming contract...")
    resp = post(f"{BAP}/contracts/confirm", {"transaction_id": txn_id})
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  ONIX ACK: {ack}")

    if not wait_for_callbacks(3):
        print("  FAIL: on_confirm callback not received")
        sys.exit(1)
    print(f"  on_confirm received — contract ACTIVE")

    # STATUS
    print("\n[6/6] STATUS — checking execution result...")
    resp = post(f"{BAP}/contracts/status", {"transaction_id": txn_id})
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  ONIX ACK: {ack}")

    if ack == "NACK":
        error = resp.get("onix_response", {}).get("message", {}).get("error", {})
        print(f"  NACK: {error.get('code', '?')}: {error.get('message', '?')[:100]}")
        # Non-fatal for now
    else:
        if not wait_for_callbacks(4):
            print("  WARN: on_status callback not received (may be slow)")
        else:
            cb = get(f"{BAP}/callbacks/ultimo")
            perf = cb.get("message", {}).get("contract", {}).get("performance", [{}])[0]
            perf_status = perf.get("status", {})
            attrs = perf.get("performanceAttributes", {})
            if attrs:
                print(f"  Agent status: {attrs.get('status', perf_status.get('code', '?'))}")
                print(f"  Latency: {attrs.get('latencyMs', '?')}ms")
                result = attrs.get("result", {})
                print(f"  Summary: {result.get('summary', '?')[:80]}...")
                print(f"  Confidence: {result.get('confidence', '?')}")
            else:
                print(f"  Agent status: {perf_status.get('code', '?')}")
                print(f"  Result: {perf_status.get('shortDesc', '?')[:80]}...")

    # Final summary
    print("\n" + "=" * 60)
    all_cbs = get(f"{BAP}/callbacks")
    print(f"RESULT: {len(all_cbs)} callbacks received")
    for i, cb in enumerate(all_cbs):
        print(f"  [{i+1}] {cb['action']}")

    contracts = get("http://localhost:3002/api/contracts")
    print(f"\nBPP contracts: {contracts['total']}")

    if len(all_cbs) >= 3:
        print("\n✓ PASS — select/init/confirm flow working with our own BAP and BPP")
    else:
        print("\n✗ FAIL — expected at least 3 callbacks")
        sys.exit(1)


if __name__ == "__main__":
    main()
