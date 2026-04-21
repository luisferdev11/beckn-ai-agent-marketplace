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

AGENT_ID = "agent-code-reviewer-001"
AGENT_INPUT = {
    "code": "def divide(a, b):\n    return a / b",
    "language": "python",
    "context": "Utility function for division",
}


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
    for name, port in [("bap-ai", 3001), ("bpp-ai", 3002), ("orchestrator", 3003), ("agents", 3004)]:
        h = get(f"http://localhost:{port}/health")
        status = h.get("status", "?")
        print(f"  {name}: {status}")
        if status not in ("ok", "degraded"):
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
    print(f"\n[3/6] SELECT — choosing {AGENT_ID}...")
    resp = post(f"{BAP}/contracts/select", {
        "agent_id": AGENT_ID,
        "offer_id": f"offer-{AGENT_ID}",
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
    print("\n[5/6] CONFIRM — confirming contract + dispatching agent...")
    print(f"  Input: {AGENT_INPUT}")
    resp = post(f"{BAP}/contracts/confirm", {
        "transaction_id": txn_id,
        "agent_id": AGENT_ID,
        "agent_input": AGENT_INPUT,
    })
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  ONIX ACK: {ack}")

    if not wait_for_callbacks(3):
        print("  FAIL: on_confirm callback not received")
        sys.exit(1)
    print(f"  on_confirm received — agent dispatched to orchestrator")

    # STATUS — poll until COMPLETED or timeout
    print("\n[6/6] STATUS — polling until agent completes (LLM may take ~5s)...")
    agent_status = None
    for attempt in range(15):
        time.sleep(3)
        resp = post(f"{BAP}/contracts/status", {"transaction_id": txn_id})
        ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
        if ack == "NACK":
            error = resp.get("onix_response", {}).get("message", {}).get("error", {})
            print(f"  NACK: {error.get('message', '?')[:100]}")
            break

        if wait_for_callbacks(4 + attempt, timeout=5):
            cb = get(f"{BAP}/callbacks/ultimo")
            perf = cb.get("message", {}).get("contract", {}).get("performance", [{}])[0]
            status_obj = perf.get("status", {})
            agent_status = status_obj.get("code", "?")
            print(f"  [{attempt+1}] Agent status: {agent_status}")
            if agent_status == "COMPLETED":
                print(f"  Result preview: {status_obj.get('shortDesc', '')[:120]}...")
                break
            elif agent_status == "FAILED":
                print(f"  Error: {status_obj.get('shortDesc', '')}")
                break
    else:
        print("  WARN: agent did not complete within timeout")

    # Final summary
    print("\n" + "=" * 60)
    all_cbs = get(f"{BAP}/callbacks")
    print(f"RESULT: {len(all_cbs)} callbacks received")
    for i, cb in enumerate(all_cbs):
        print(f"  [{i+1}] {cb['action']}")

    contracts = get("http://localhost:3002/api/contracts")
    print(f"\nBPP contracts: {contracts['total']}")

    if len(all_cbs) >= 3 and agent_status == "COMPLETED":
        print("\n✓ PASS — full flow working including real agent execution")
    elif len(all_cbs) >= 3:
        print("\n~ PARTIAL — select/init/confirm OK but agent not yet COMPLETED")
    else:
        print("\n✗ FAIL — expected at least 3 callbacks")
        sys.exit(1)


if __name__ == "__main__":
    main()
