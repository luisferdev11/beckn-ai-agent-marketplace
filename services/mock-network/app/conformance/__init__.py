"""BPP conformance kit — callable module.

Single source of truth for the 11-test conformance suite that a partner
BPP must pass before admission. Two layers:

  ``kit.run(ctx)``                 low-level: runs the suite against a
                                   TestContext, returns (exit_code, results).
                                   Pure httpx + jsonschema — NO database
                                   deps, so the standalone CLI wrapper at
                                   ``scripts/bpp_conformance_kit.py`` can run
                                   it from a developer's laptop.

  ``runner.run_for_subscriber``    high-level: resolves a subscriber's
                                   backend URL from the Registry, runs the
                                   suite, persists a ``conformance_runs``
                                   row. Pulls in asyncpg, so it is imported
                                   lazily (below) — importing this package
                                   must not require the DB stack.

See docs/PLAN-BPP-REGISTRY-LIFECYCLE.md, Epic B.
"""
from app.conformance.kit import TestContext, TestResult, run  # noqa: F401

__all__ = [
    "TestContext",
    "TestResult",
    "run",
    "run_for_bpp",
    "run_for_subscriber",
]

# Lazy re-export of the DB-backed runner entry points (PEP 562). Keeps
# ``from app.conformance import run_for_subscriber`` working for the
# Registry while leaving the package importable in environments without
# asyncpg (the standalone conformance CLI).
_RUNNER_EXPORTS = {"run_for_bpp", "run_for_subscriber"}


def __getattr__(name: str):
    if name in _RUNNER_EXPORTS:
        from app.conformance import runner
        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
