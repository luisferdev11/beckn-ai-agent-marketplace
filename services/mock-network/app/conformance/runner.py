"""High-level conformance orchestration.

``run_for_bpp``        builds an httpx client + TestContext, runs the kit,
                       and returns a structured summary (no persistence).

``run_for_subscriber`` resolves the subscriber's backend URL from the
                       Registry, persists a ``conformance_runs`` row, runs
                       the kit, records the verdict, writes an audit entry,
                       and parks the subscriber in ``failing_conformance``
                       when the 'must' tier fails (flipping back to
                       ``pending_admission`` on a later pass).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.conformance import repository
from app.conformance.kit import TestContext, run as run_kit

logger = logging.getLogger(__name__)

# Subscriber statuses where a conformance run is allowed to mutate status.
# We never clobber an 'active'/'suspended'/'deprecated' subscriber if an
# operator re-runs the kit against them out of band.
_MUTABLE_STATUSES = {"pending_admission", "failing_conformance"}


def _summarize(results: list, *, exit_code: int) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    must_total = sum(1 for r in results if r.criticality == "must")
    must_passed_n = sum(1 for r in results if r.criticality == "must" and r.passed)
    should_total = sum(1 for r in results if r.criticality == "should")
    should_passed_n = sum(1 for r in results if r.criticality == "should" and r.passed)
    return {
        "total_tests": total,
        "passed_tests": passed,
        # When the BPP is unreachable (exit_code 2) there are no results;
        # treat that as a must failure so admission cannot proceed.
        "must_passed": bool(results) and must_passed_n == must_total and exit_code != 2,
        "should_passed": should_passed_n == should_total,
        "results": [r.to_dict() for r in results],
        "exit_code": exit_code,
    }


async def run_for_bpp(
    bpp_url: str,
    bpp_id: str,
    *,
    catalog_path: str = "/api/catalog",
) -> dict:
    """Run the kit against an arbitrary BPP backend URL. No DB writes."""
    async with httpx.AsyncClient() as http:
        ctx = TestContext(
            bpp_url=bpp_url,
            bpp_id=bpp_id,
            catalog_path=catalog_path,
            http=http,
        )
        exit_code, results = await run_kit(ctx, verbose=True)
    return _summarize(results, exit_code=exit_code)


async def run_for_subscriber(subscriber_id: str) -> Optional[dict]:
    """Resolve, run, persist. Returns the summary dict, or None if the
    subscriber is unknown / has no probeable backend URL."""
    from app.registry import repository as registry_repository

    subscriber = await registry_repository.get_subscriber(subscriber_id)
    if subscriber is None:
        logger.warning("conformance: unknown subscriber %s", subscriber_id)
        return None

    backend_url = subscriber.get("backend_health_url")
    if not backend_url:
        logger.warning(
            "conformance: subscriber %s has no backend_health_url; cannot probe",
            subscriber_id,
        )
        # Persist a record so the admin sees that conformance could not run.
        run_id = await repository.create_run(subscriber_id)
        await repository.finish_run(
            run_id, total_tests=0, passed_tests=0,
            must_passed=False, should_passed=False,
            results=[{"name": "reachability", "criticality": "must", "passed": False,
                      "detail": "no backend_health_url declared", "latency_ms": None}],
        )
        await _record_audit(subscriber_id, run_id, must_passed=False)
        await _maybe_flip_status(subscriber_id, subscriber["status"], must_passed=False)
        return _summarize([], exit_code=2)

    run_id = await repository.create_run(subscriber_id)
    logger.info("conformance: run %s started for %s (%s)", run_id, subscriber_id, backend_url)

    summary = await run_for_bpp(backend_url, subscriber_id)

    await repository.finish_run(
        run_id,
        total_tests=summary["total_tests"],
        passed_tests=summary["passed_tests"],
        must_passed=summary["must_passed"],
        should_passed=summary["should_passed"],
        results=summary["results"],
    )
    await _record_audit(subscriber_id, run_id, must_passed=summary["must_passed"])
    await _maybe_flip_status(subscriber_id, subscriber["status"],
                             must_passed=summary["must_passed"])

    logger.info(
        "conformance: run %s finished for %s — must_passed=%s (%d/%d)",
        run_id, subscriber_id, summary["must_passed"],
        summary["passed_tests"], summary["total_tests"],
    )
    return summary


async def _record_audit(subscriber_id: str, run_id: int, *, must_passed: bool) -> None:
    from app.admission import repository as admission_repository
    await admission_repository.record_audit(
        subscriber_id=subscriber_id,
        action="conformance_run",
        actor="system",
        details={"run_id": run_id, "must_passed": must_passed},
    )


async def _maybe_flip_status(subscriber_id: str, current_status: str, *, must_passed: bool) -> None:
    """Park a failing BPP in ``failing_conformance``; restore a now-passing
    one to ``pending_admission`` so an admin can approve it. Never touches a
    subscriber outside the admission-related states."""
    if current_status not in _MUTABLE_STATUSES:
        return
    target = "pending_admission" if must_passed else "failing_conformance"
    if target == current_status:
        return
    from app.registry import repository as registry_repository
    await registry_repository.update_subscriber(subscriber_id, status=target)
