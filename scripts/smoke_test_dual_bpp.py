#!/usr/bin/env python3
"""
Dual-BPP smoke test — verifies the full Beckn flow when two BPPs coexist.

Flow under test:
  1. Health checks across the whole stack including discovery + bpp-serg + agents-serg.
  2. discover via the Discovery Service: BAP receives one on_discover per BPP.
  3. Full Beckn flow against a Tecla agent (General Tecla Industries / agents).
  4. Full Beckn flow against a Serg agent (Serg Ops / agents-serg).
  5. Real LLM execution end-to-end for both BPPs.

Usage:
    python scripts/smoke_test_dual_bpp.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

BAP = "http://localhost:3001/api"


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def _wait_for_total_callbacks(target: int, timeout: int = 20) -> int:
    """Block until the BAP has received at least `target` callbacks."""
    start = time.time()
    last = 0
    while time.time() - start < timeout:
        last = _get(f"{BAP}/callbacks/count").get("callbacks_recibidos", 0)
        if last >= target:
            return last
        time.sleep(1)
    return last


def _section(title: str):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _run_full_flow(
    label: str,
    agent_id: str,
    offer_id: str,
    agent_input: dict,
    bpp_id: Optional[str] = None,
    bpp_uri: Optional[str] = None,
) -> str:
    """Execute select → init → confirm → status against a single agent_id. Returns final status."""
    print(f"\n--- {label} ({agent_id}) ---")

    starting = _get(f"{BAP}/callbacks/count").get("callbacks_recibidos", 0)

    select_body = {"agent_id": agent_id, "offer_id": offer_id}
    if bpp_id:
        select_body["bpp_id"] = bpp_id
        select_body["bpp_uri"] = bpp_uri
    resp = _post(f"{BAP}/contracts/select", select_body)
    txn_id = resp["transactionId"]
    print(f"  select transactionId: {txn_id}  ack={resp.get('onix_response', {}).get('message', {}).get('ack', {}).get('status')}")

    if _wait_for_total_callbacks(starting + 1) < starting + 1:
        print("  FAIL: on_select not received")
        return "TIMEOUT_SELECT"
    # Read price from the transaction record (resilient to multiple callbacks landing concurrently).
    # The repository returns the contracts row flat, with consideration as a JSONB column.
    txn_record = _get(f"{BAP}/transactions/{txn_id}")
    raw_consideration = txn_record.get("consideration") if txn_record else None
    if isinstance(raw_consideration, str):
        raw_consideration = json.loads(raw_consideration)
    consideration = raw_consideration or [{}]
    price = (consideration[0] if consideration else {}).get("price", {})
    print(f"  on_select  price: {price.get('currency', '?')} {price.get('value', '?')}")

    resp = _post(f"{BAP}/contracts/init", {"transaction_id": txn_id})
    if _wait_for_total_callbacks(starting + 2) < starting + 2:
        print("  FAIL: on_init not received")
        return "TIMEOUT_INIT"
    print("  on_init    ✓")

    resp = _post(f"{BAP}/contracts/confirm", {
        "transaction_id": txn_id,
        "agent_id": agent_id,
        "agent_input": agent_input,
    })
    if _wait_for_total_callbacks(starting + 3) < starting + 3:
        print("  FAIL: on_confirm not received")
        return "TIMEOUT_CONFIRM"
    print("  on_confirm ✓ (agent dispatched)")

    final_code = "?"
    for attempt in range(20):
        time.sleep(2)
        _post(f"{BAP}/contracts/status", {"transaction_id": txn_id})
        # Pull from /api/callbacks. Postgres rows expose transaction_id (snake_case)
        # and message as a JSON string we have to parse explicitly.
        all_cbs = _get(f"{BAP}/callbacks")
        on_status = [
            c for c in all_cbs
            if c.get("transaction_id") == txn_id and c.get("action") == "on_status"
        ]
        if not on_status:
            continue
        last_status = on_status[-1]
        raw_msg = last_status.get("message") or "{}"
        msg = json.loads(raw_msg) if isinstance(raw_msg, str) else raw_msg
        perf = msg.get("contract", {}).get("performance", [{}])[0]
        status_obj = perf.get("status", {})
        final_code = status_obj.get("code", "?")
        print(f"  [{attempt + 1}] on_status: {final_code}")
        if final_code in ("COMPLETED", "FAILED"):
            preview = (status_obj.get("shortDesc") or "").strip().replace("\n", " ")[:160]
            print(f"  preview: {preview}")
            return final_code

    return final_code


def main():
    _section("[1/4] HEALTH CHECKS")
    services = [
        ("bap-marketplace", 3001),
        ("bpp-provider",    3002),
        ("orchestrator",    3003),
        ("agents",          3004),
        ("bpp-serg",        3005),
        ("agents-serg",     3006),
        ("discovery",       3007),
    ]
    for name, port in services:
        try:
            h = _get(f"http://localhost:{port}/health")
            print(f"  {name:20s} {h.get('status', '?')}")
        except Exception as exc:
            print(f"  {name:20s} UNREACHABLE ({exc})")
            sys.exit(1)

    _section("[2/4] DISCOVER — indexed CDS returns both BPPs' catalogs")
    resp = _post(f"{BAP}/contracts/discover", {})
    txn_id = resp["transactionId"]
    ack = resp.get("onix_response", {}).get("message", {}).get("ack", {}).get("status")
    print(f"  discover transactionId: {txn_id}  ack={ack}")

    # Pieza 2: the CDS replies with ONE on_discover containing one catalog
    # per BPP (previously the Discovery Service fanned out and the BAP
    # accumulated one callback per BPP). The invariant we check is now
    # "at least two distinct providers appear across all returned catalogs".
    deadline = time.time() + 15
    callbacks_for_txn = []
    seen_providers: list[str] = []
    while time.time() < deadline:
        all_cbs = _get(f"{BAP}/callbacks")
        callbacks_for_txn = [
            c for c in all_cbs
            if c.get("transaction_id") == txn_id and c.get("action") == "on_discover"
        ]
        seen_providers = []
        for cb in callbacks_for_txn:
            raw_msg = cb.get("message") or "{}"
            msg = json.loads(raw_msg) if isinstance(raw_msg, str) else raw_msg
            catalogs = msg.get("catalogs") or [msg.get("catalog", {})]
            for catalog in catalogs:
                provider = catalog.get("provider", {}).get("descriptor", {}).get("name", "?")
                seen_providers.append(provider)
        if len(set(p for p in seen_providers if p != "?")) >= 2:
            break
        time.sleep(1)

    print(f"  on_discover callbacks: {len(callbacks_for_txn)} (expect 1 with N catalogs)")
    distinct_providers = set(p for p in seen_providers if p != "?")
    for cb in callbacks_for_txn:
        raw_msg = cb.get("message") or "{}"
        msg = json.loads(raw_msg) if isinstance(raw_msg, str) else raw_msg
        for catalog in msg.get("catalogs", []):
            provider = catalog.get("provider", {}).get("descriptor", {}).get("name", "?")
            agent_count = len(catalog.get("resources", []))
            print(f"    - provider: {provider:30s} agents: {agent_count}")

    discover_ok = (
        len(callbacks_for_txn) >= 1
        and len(distinct_providers) >= 2
        and "Serg Ops" in distinct_providers
    )

    _section("[3/4] FLOW — Tecla agent (General Tecla Industries)")
    tecla_status = _run_full_flow(
        "Tecla / Code Reviewer",
        agent_id="agent-code-reviewer-001",
        offer_id="offer-code-review-basic",
        agent_input={
            "code": "def divide(a, b):\n    return a / b",
            "language": "python",
            "context": "Utility function — please flag the missing zero-division check.",
        },
    )

    _section("[4/4] FLOW — Serg agent (Serg Ops)")
    serg_status = _run_full_flow(
        "Serg / Summarizer",
        agent_id="summarizer-v1",
        offer_id="offer-summarizer-v1",
        agent_input={
            "text": (
                "Beckn protocol is an open network protocol that decouples consumer "
                "applications from provider applications using standardized message "
                "schemas. Adopters publish to discovery services and process orders "
                "through a transactional, signature-verified flow."
            ),
            "max_points": 3,
        },
        bpp_id="bpp-serg.example.com",
        bpp_uri="http://onix-bpp-serg:8083/bpp/receiver",
    )

    _section("RESULT")
    print(f"  discover federation : {'PASS' if discover_ok else 'FAIL'}")
    print(f"  Tecla flow          : {tecla_status}")
    print(f"  Serg flow           : {serg_status}")

    overall_ok = discover_ok and tecla_status == "COMPLETED" and serg_status == "COMPLETED"
    print()
    if overall_ok:
        print("  ✓ ALL GREEN — dual-BPP marketplace is working end-to-end")
        return 0
    print("  ✗ At least one stage did not pass — see logs above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
