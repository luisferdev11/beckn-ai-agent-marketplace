"""Conformance test suite — pure HTTP probes against a BPP's surface.

Lifted verbatim (logic-wise) from the original standalone script so the
behaviour the CLI exercised is preserved exactly; the only change is that
the argparse/main entrypoint now lives in the thin CLI wrapper at
``scripts/bpp_conformance_kit.py``, which imports from here.

What we DO test (directly against the BPP's HTTP surface):
    - /health responds < 500 ms
    - Beckn webhooks ACK valid envelopes
    - init/confirm/status/cancel reject unknown transactions without crashing
    - on_publish webhook ACKs the callback shape
    - Malformed requests don't crash with 500
    - If the BPP exposes /api/catalog, items validate against AgentFacts v1

What we do NOT test (out of scope):
    - Signature verification (needs ONIX in the loop)
    - The full publish→index→on_publish round trip
    - Multi-step transaction lifecycle persistence
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

try:
    from jsonschema import Draft202012Validator
    _SCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover - kit must run without optional deps
    _SCHEMA_AVAILABLE = False


# ─── Configuration ───────────────────────────────────────────────────

HEALTH_BUDGET_MS = 500
ACK_BUDGET_S = 5.0
# schemas/agentfacts-v1.json — resolved relative to the repo root. In the
# mock-network container the schema is copied to /app/schemas/.
DEFAULT_AGENT_FACTS_SCHEMA = (
    Path(__file__).resolve().parents[2] / "schemas" / "agentfacts-v1.json"
)


@dataclass
class TestContext:
    __test__ = False

    bpp_url: str
    bpp_id: str
    bap_id: str = "conformance-kit.local"
    bap_uri: str = "http://localhost:9999/conformance"
    network_id: str = "beckn.one/testnet"
    catalog_path: str = "/api/catalog"
    schema_path: Optional[Path] = None
    http: httpx.AsyncClient = field(default=None, repr=False)  # type: ignore[assignment]


@dataclass
class TestResult:
    # Tell pytest this is not a test class despite the ``Test`` prefix.
    __test__ = False

    name: str
    criticality: str  # "must" | "should"
    passed: bool
    detail: str = ""
    latency_ms: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "criticality": self.criticality,
            "passed": self.passed,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


_TESTS: list[dict] = []


def test(name: str, *, criticality: str = "must"):
    """Decorator: registers an async test function in declaration order."""
    def wrap(fn):
        _TESTS.append({"name": name, "criticality": criticality, "fn": fn})
        return fn
    return wrap


# ─── Envelope builders ───────────────────────────────────────────────


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _context(ctx: TestContext, action: str, transaction_id: Optional[str] = None) -> dict:
    return {
        "networkId": ctx.network_id,
        "action": action,
        "version": "2.0.0",
        "bapId": ctx.bap_id,
        "bapUri": ctx.bap_uri,
        "bppId": ctx.bpp_id,
        "bppUri": f"{ctx.bpp_url.rstrip('/')}/bpp/receiver",
        "transactionId": transaction_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "ttl": "PT30S",
    }


def _select_envelope(ctx: TestContext, *, agent_id: str = "agent-conformance-probe") -> dict:
    return {
        "context": _context(ctx, "select"),
        "message": {
            "contract": {
                "id": f"contract-{uuid.uuid4().hex[:8]}",
                "participants": [
                    {"id": "participant-buyer-conformance",
                     "descriptor": {"name": "Conformance Kit", "code": "buyer"}}
                ],
                "commitments": [{
                    "id": "commitment-001",
                    "descriptor": {"name": "AI Agent Service", "code": "AAS-001"},
                    "status": {"code": "DRAFT"},
                    "resources": [{
                        "id": agent_id,
                        "descriptor": {"name": "AI Agent", "code": agent_id},
                        "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": f"offer-{agent_id}", "resourceIds": [agent_id]},
                }],
            }
        },
    }


def _bare_txn_envelope(ctx: TestContext, action: str, transaction_id: str) -> dict:
    """Envelope for init/confirm/status/cancel with no prior select."""
    return {
        "context": _context(ctx, action, transaction_id=transaction_id),
        "message": {"contract": {
            "id": f"contract-{transaction_id[:8]}",
            "commitments": [],
        }},
    }


def _on_publish_envelope(ctx: TestContext) -> dict:
    return {
        "context": _context(ctx, "on_publish"),
        "message": {
            "results": [{
                "catalogId": "catalog-conformance",
                "status": "ACCEPTED",
                "stats": {"itemCount": 0, "itemCountAccepted": 0, "itemCountRejected": 0},
                "errors": [],
            }]
        },
    }


# ─── Assertion helpers ───────────────────────────────────────────────


def _ack_status(body: dict) -> Optional[str]:
    return (body or {}).get("message", {}).get("ack", {}).get("status")


def _error_code(body: dict) -> Optional[str]:
    # Error may live top-level (Beckn v2 envelope) or nested in message._error
    err = body.get("error") if isinstance(body, dict) else None
    if err and isinstance(err, dict):
        return err.get("code")
    msg = body.get("message", {}) if isinstance(body, dict) else {}
    nested = msg.get("_error") if isinstance(msg, dict) else None
    if isinstance(nested, dict):
        return nested.get("code")
    return None


async def _post(ctx: TestContext, path: str, body: dict, *, timeout: float = ACK_BUDGET_S) -> tuple[int, dict, float]:
    url = ctx.bpp_url.rstrip("/") + path
    started = time.perf_counter()
    resp = await ctx.http.post(url, json=body, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    try:
        return resp.status_code, resp.json(), elapsed_ms
    except Exception:
        return resp.status_code, {}, elapsed_ms


# ─── Tests ───────────────────────────────────────────────────────────


@test("Health endpoint responds within budget", criticality="must")
async def t_health(ctx: TestContext) -> TestResult:
    url = ctx.bpp_url.rstrip("/") + "/health"
    started = time.perf_counter()
    r = await ctx.http.get(url, timeout=2.0)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if r.status_code != 200:
        return TestResult("Health endpoint responds within budget", "must", False,
                          detail=f"HTTP {r.status_code} (expected 200)",
                          latency_ms=elapsed_ms)
    if elapsed_ms > HEALTH_BUDGET_MS:
        return TestResult("Health endpoint responds within budget", "should", False,
                          detail=f"latency {elapsed_ms}ms exceeds {HEALTH_BUDGET_MS}ms budget",
                          latency_ms=elapsed_ms)
    return TestResult("Health endpoint responds within budget", "must", True,
                      latency_ms=elapsed_ms)


@test("select webhook returns Beckn ACK envelope", criticality="must")
async def t_select_ack(ctx: TestContext) -> TestResult:
    status, body, elapsed = await _post(ctx, "/api/webhook/select", _select_envelope(ctx))
    if status != 200:
        return TestResult("select webhook returns Beckn ACK envelope", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    ack = _ack_status(body)
    if ack not in ("ACK", "NACK"):
        return TestResult("select webhook returns Beckn ACK envelope", "must", False,
                          detail=f"missing/invalid ack: {body}", latency_ms=elapsed)
    return TestResult("select webhook returns Beckn ACK envelope", "must", True,
                      latency_ms=elapsed, detail=f"ack={ack}")


@test("init rejects unknown transaction with code 30002", criticality="must")
async def t_init_unknown_txn(ctx: TestContext) -> TestResult:
    txn = f"conformance-ghost-{uuid.uuid4().hex[:6]}"
    status, body, elapsed = await _post(ctx, "/api/webhook/init",
                                        _bare_txn_envelope(ctx, "init", txn))
    if status >= 500:
        return TestResult("init rejects unknown transaction with code 30002", "must", False,
                          detail=f"HTTP {status} (expected 2xx)", latency_ms=elapsed)
    if _ack_status(body) is None:
        return TestResult("init rejects unknown transaction with code 30002", "must", False,
                          detail=f"no ack in response: {body}", latency_ms=elapsed)
    code = _error_code(body)
    if code and code != "30002":
        return TestResult("init rejects unknown transaction with code 30002", "must", False,
                          detail=f"got error code {code!r}, expected '30002'",
                          latency_ms=elapsed)
    return TestResult("init rejects unknown transaction with code 30002", "must", True,
                      latency_ms=elapsed)


@test("confirm rejects unknown transaction (no crash)", criticality="must")
async def t_confirm_unknown_txn(ctx: TestContext) -> TestResult:
    txn = f"conformance-ghost-{uuid.uuid4().hex[:6]}"
    status, body, elapsed = await _post(ctx, "/api/webhook/confirm",
                                        _bare_txn_envelope(ctx, "confirm", txn))
    if status >= 500:
        return TestResult("confirm rejects unknown transaction (no crash)", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    if _ack_status(body) is None:
        return TestResult("confirm rejects unknown transaction (no crash)", "must", False,
                          detail=f"no ack: {body}", latency_ms=elapsed)
    return TestResult("confirm rejects unknown transaction (no crash)", "must", True,
                      latency_ms=elapsed)


@test("status rejects unknown transaction (no crash)", criticality="must")
async def t_status_unknown_txn(ctx: TestContext) -> TestResult:
    txn = f"conformance-ghost-{uuid.uuid4().hex[:6]}"
    status, body, elapsed = await _post(ctx, "/api/webhook/status",
                                        _bare_txn_envelope(ctx, "status", txn))
    if status >= 500:
        return TestResult("status rejects unknown transaction (no crash)", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    return TestResult("status rejects unknown transaction (no crash)", "must", True,
                      latency_ms=elapsed)


@test("cancel rejects unknown transaction (no crash)", criticality="must")
async def t_cancel_unknown_txn(ctx: TestContext) -> TestResult:
    txn = f"conformance-ghost-{uuid.uuid4().hex[:6]}"
    status, body, elapsed = await _post(ctx, "/api/webhook/cancel",
                                        _bare_txn_envelope(ctx, "cancel", txn))
    if status >= 500:
        return TestResult("cancel rejects unknown transaction (no crash)", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    return TestResult("cancel rejects unknown transaction (no crash)", "must", True,
                      latency_ms=elapsed)


@test("on_publish webhook accepts the standard callback shape", criticality="must")
async def t_on_publish_ack(ctx: TestContext) -> TestResult:
    status, body, elapsed = await _post(ctx, "/api/webhook/on_publish", _on_publish_envelope(ctx))
    if status >= 500:
        return TestResult("on_publish webhook accepts the standard callback shape", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    if _ack_status(body) is None:
        return TestResult("on_publish webhook accepts the standard callback shape", "must", False,
                          detail=f"no ack: {body}", latency_ms=elapsed)
    return TestResult("on_publish webhook accepts the standard callback shape", "must", True,
                      latency_ms=elapsed)


@test("Unknown action does not crash (returns ACK or 4xx)", criticality="must")
async def t_unknown_action(ctx: TestContext) -> TestResult:
    status, body, elapsed = await _post(ctx, "/api/webhook/totallyBogusAction",
                                        _bare_txn_envelope(ctx, "totallyBogusAction", "x"))
    if status >= 500:
        return TestResult("Unknown action does not crash (returns ACK or 4xx)", "must", False,
                          detail=f"HTTP {status}", latency_ms=elapsed)
    return TestResult("Unknown action does not crash (returns ACK or 4xx)", "must", True,
                      latency_ms=elapsed)


@test("Malformed JSON request does not crash", criticality="must")
async def t_malformed_json(ctx: TestContext) -> TestResult:
    url = ctx.bpp_url.rstrip("/") + "/api/webhook/select"
    started = time.perf_counter()
    r = await ctx.http.post(
        url,
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
        timeout=ACK_BUDGET_S,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if r.status_code >= 500:
        return TestResult("Malformed JSON request does not crash", "must", False,
                          detail=f"HTTP {r.status_code}", latency_ms=elapsed_ms)
    return TestResult("Malformed JSON request does not crash", "must", True,
                      latency_ms=elapsed_ms)


@test("Catalog endpoint exposes AgentFacts items", criticality="should")
async def t_catalog_shape(ctx: TestContext) -> TestResult:
    url = ctx.bpp_url.rstrip("/") + ctx.catalog_path
    r = await ctx.http.get(url, timeout=5.0)
    if r.status_code != 200:
        return TestResult("Catalog endpoint exposes AgentFacts items", "should", False,
                          detail=f"GET {ctx.catalog_path} returned HTTP {r.status_code}")
    try:
        body = r.json()
    except Exception:
        return TestResult("Catalog endpoint exposes AgentFacts items", "should", False,
                          detail="response is not valid JSON")
    # Two common shapes: {"resources": [...]} (Tecla) or {"catalogs":[{"resources":[...]}]}
    resources = body.get("resources")
    if resources is None and "catalogs" in body:
        catalogs = body.get("catalogs") or []
        resources = [r for c in catalogs for r in (c.get("resources") or [])]
    if not resources:
        return TestResult("Catalog endpoint exposes AgentFacts items", "should", False,
                          detail="no resources found in catalog response")
    has_facts = sum(1 for r in resources if isinstance(r, dict) and r.get("resourceAttributes"))
    if has_facts == 0:
        return TestResult("Catalog endpoint exposes AgentFacts items", "should", False,
                          detail="no resource has resourceAttributes")
    return TestResult("Catalog endpoint exposes AgentFacts items", "should", True,
                      detail=f"{has_facts} item(s) carry resourceAttributes")


@test("Catalog items validate against AgentFacts v1 schema", criticality="should")
async def t_catalog_schema(ctx: TestContext) -> TestResult:
    if not _SCHEMA_AVAILABLE:
        return TestResult("Catalog items validate against AgentFacts v1 schema", "should", False,
                          detail="jsonschema not installed; skipping (install with: pip install jsonschema)")
    schema_path = ctx.schema_path or DEFAULT_AGENT_FACTS_SCHEMA
    if not schema_path.exists():
        return TestResult("Catalog items validate against AgentFacts v1 schema", "should", False,
                          detail=f"schema not found at {schema_path}")
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema)

    url = ctx.bpp_url.rstrip("/") + ctx.catalog_path
    r = await ctx.http.get(url, timeout=5.0)
    if r.status_code != 200:
        return TestResult("Catalog items validate against AgentFacts v1 schema", "should", False,
                          detail=f"GET {ctx.catalog_path} returned HTTP {r.status_code}")
    body = r.json()
    resources = body.get("resources") or []
    if "catalogs" in body and not resources:
        resources = [r for c in body.get("catalogs", []) for r in (c.get("resources") or [])]

    failures: list[str] = []
    valid_count = 0
    for res in resources:
        facts = (res or {}).get("resourceAttributes")
        if not facts:
            continue
        errs = list(validator.iter_errors(facts))
        if errs:
            err_summary = "; ".join(f"{'.'.join(str(p) for p in e.absolute_path) or '$'}: {e.message[:60]}"
                                    for e in errs[:3])
            failures.append(f"{res.get('id', '?')}: {err_summary}")
        else:
            valid_count += 1
    if failures:
        return TestResult("Catalog items validate against AgentFacts v1 schema", "should", False,
                          detail=f"{len(failures)} items failed validation; first: {failures[0]}")
    if valid_count == 0:
        return TestResult("Catalog items validate against AgentFacts v1 schema", "should", False,
                          detail="no items to validate")
    return TestResult("Catalog items validate against AgentFacts v1 schema", "should", True,
                      detail=f"{valid_count} item(s) valid")


# ─── Runner ──────────────────────────────────────────────────────────


def _bar(ok: bool, criticality: str) -> str:
    if ok:
        return "  PASS"
    return "  FAIL" if criticality == "must" else "  WARN"


async def run(ctx: TestContext, *, verbose: bool = True) -> tuple[int, list[TestResult]]:
    """Run the full suite against ``ctx``. Returns (exit_code, results).

    exit_code: 0 all-must-passed, 1 a must failed, 2 BPP unreachable.
    ``verbose`` prints a human report (used by the CLI). The runner sets
    it True too so container logs show the kit progress (Epic B2).
    """
    results: list[TestResult] = []
    if verbose:
        print(f"\nRunning BPP Conformance Kit against {ctx.bpp_url}")
        print(f"  bpp_id: {ctx.bpp_id}")
        print(f"  catalog endpoint to probe: {ctx.catalog_path}")
        print()

    # Liveness check first; abort if unreachable.
    try:
        r = await ctx.http.get(ctx.bpp_url.rstrip("/") + "/health", timeout=3.0)
        if r.status_code >= 500:
            if verbose:
                print(f"  BPP unreachable: /health returned {r.status_code}")
            return 2, []
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        if verbose:
            print(f"  BPP unreachable: {exc}")
        return 2, []

    for t in _TESTS:
        try:
            result = await t["fn"](ctx)
        except Exception as exc:  # noqa: BLE001
            result = TestResult(t["name"], t["criticality"], False,
                                detail=f"test crashed: {type(exc).__name__}: {exc}")
        results.append(result)
        if verbose:
            lat = f"  ({result.latency_ms}ms)" if result.latency_ms is not None else ""
            print(f"{_bar(result.passed, result.criticality)} [{result.criticality}] "
                  f"{result.name}{lat}")
            if not result.passed and result.detail:
                print(f"          {result.detail}")

    must_failed = sum(1 for r in results if not r.passed and r.criticality == "must")
    should_failed = sum(1 for r in results if not r.passed and r.criticality == "should")
    total_must = sum(1 for r in results if r.criticality == "must")
    total_should = sum(1 for r in results if r.criticality == "should")

    if verbose:
        print()
        print("─" * 60)
        print(f"  must:   {total_must - must_failed}/{total_must} passed")
        print(f"  should: {total_should - should_failed}/{total_should} passed")
        print()
        if must_failed == 0:
            if should_failed == 0:
                print("  ✓ Conformance kit PASSED — your BPP is ready to request admission.")
            else:
                print("  ⚠ Conformance kit PASSED (with warnings) — admission OK; address warnings before going to prod.")
        else:
            print("  ✗ Conformance kit FAILED — fix the 'must' failures above before submitting.")

    return (1 if must_failed else 0), results
