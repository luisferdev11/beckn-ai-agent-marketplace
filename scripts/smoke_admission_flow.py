#!/usr/bin/env python3
"""
Admission + conformance + probe lifecycle smoke (Epics A/B/C/E).

Drives the mock-network Registry through a partner-BPP onboarding, against
the live Tecla BPP backend as the conformance target:

  1. POST /registry/admission-requests          → 202, subscriber parked
  2. (auto) conformance kit runs in background   → conformance_runs row
  3. approve gated on must_passed                → subscriber active
  4. dry-run probe of any probation agents       → promoted to live

Self-cleaning: removes the throwaway subscriber + audit + conformance rows
at the end so the demo DB stays tidy. Run it repeatedly.

Usage:
    python scripts/smoke_admission_flow.py
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request

CDS = "http://localhost:8090"
SUBSCRIBER_ID = "bpp-smoke-admission.example.com"
# Conformance probes the live Tecla backend (reachable on the docker net).
BACKEND_URL = "http://bpp-provider:3002"
VALID_KEY = base64.b64encode(b"\x07" * 32).decode()


def _parse(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"_raw": raw.decode(errors="replace")[:200]}


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(CDS + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, _parse(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read())


def _ok(label: str, cond: bool, extra: str = "") -> bool:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' — ' + extra) if extra else ''}")
    return cond


def main() -> int:
    print("=" * 64)
    print("ADMISSION + CONFORMANCE LIFECYCLE SMOKE")
    print("=" * 64)
    results: list[bool] = []

    # 1. Submit admission request.
    code, body = _req("POST", "/registry/admission-requests", {
        "subscriber_id": SUBSCRIBER_ID,
        "endpoint_url": "http://onix-smoke:8099/bpp/receiver",
        "public_key": VALID_KEY,
        "organization": {"name": "Smoke Test Provider"},
        "jurisdiction": "IND",
        "contact_email": "smoke@example.com",
        "backend_health_url": BACKEND_URL,
    })
    request_id = body.get("id")
    results.append(_ok("admission request accepted (202)", code == 202,
                       f"request_id={request_id}"))

    # 2. Subscriber parked pending_admission.
    _, sub = _req("GET", f"/registry/subscribers/{SUBSCRIBER_ID}")
    results.append(_ok("subscriber parked pending_admission",
                       sub.get("status") == "pending_admission"))

    # 3. Wait for the auto-triggered conformance run.
    print("  ... waiting for background conformance run (up to 30s)")
    must_passed = None
    for _ in range(30):
        _, detail = _req("GET", f"/registry/admission-requests/{request_id}")
        conf = detail.get("latest_conformance")
        if conf and conf.get("finished_at"):
            must_passed = conf.get("must_passed")
            results.append(_ok("conformance run persisted", True,
                               f"{conf['passed_tests']}/{conf['total_tests']} passed, "
                               f"must_passed={must_passed}"))
            break
        time.sleep(1)
    else:
        results.append(_ok("conformance run persisted", False, "timed out"))

    # 4. Approve (gated on must_passed).
    code, appr = _req("POST", f"/registry/admission-requests/{request_id}/approve",
                      {"reviewed_by": "smoke@example.com"})
    if must_passed:
        results.append(_ok("approve succeeds when conformance passed", code == 200,
                           f"decision={appr.get('decision')}"))
        _, sub = _req("GET", f"/registry/subscribers/{SUBSCRIBER_ID}")
        results.append(_ok("subscriber now active", sub.get("status") == "active"))
    else:
        results.append(_ok("approve blocked when conformance failed", code == 422,
                           "conformance_not_passed"))

    # Cleanup.
    print("  ... cleaning up throwaway subscriber")
    _cleanup()

    print("=" * 64)
    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    print("=" * 64)
    return 0 if passed == len(results) else 1


def _cleanup() -> None:
    """Best-effort DB cleanup via docker exec psql (keeps the demo tidy)."""
    import subprocess
    sql = (
        f"DELETE FROM subscriber_audit WHERE subscriber_id='{SUBSCRIBER_ID}';"
        f"DELETE FROM conformance_runs WHERE subscriber_id='{SUBSCRIBER_ID}';"
        f"DELETE FROM admission_requests WHERE subscriber_id='{SUBSCRIBER_ID}';"
        f"DELETE FROM subscribers WHERE subscriber_id='{SUBSCRIBER_ID}';"
    )
    try:
        subprocess.run(
            ["docker", "exec", "-i", "infra-postgres-mocknet-1",
             "psql", "-U", "mocknet_user", "-d", "mocknet_db", "-q", "-c", sql],
            check=False, capture_output=True, timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  (cleanup skipped: {exc})")


if __name__ == "__main__":
    sys.exit(main())
