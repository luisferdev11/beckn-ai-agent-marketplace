#!/usr/bin/env python3
"""
BPP Conformance Test Kit — Beckn AI Agent Marketplace (CLI wrapper).

Audience: a developer integrating a new BPP. Run this against your BPP
BEFORE submitting your registry record so you know it speaks the protocol
correctly.

This is a thin CLI front-end. The actual test suite lives in the callable
module ``services/mock-network/app/conformance/kit.py`` so the same logic
backs both this CLI and the Registry's automatic conformance gate on
admission. (docs/PLAN-BPP-REGISTRY-LIFECYCLE.md, Epic B.)

Usage:
    python scripts/bpp_conformance_kit.py \\
        --bpp-url http://localhost:3002 \\
        --bpp-id bpp.example.com

Exit code:
    0   all "must" tests passed — you're ready to request admission
    1   one or more critical tests failed — fix before submitting
    2   could not reach the BPP
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

# Make the mock-network app package importable so the CLI and the Registry
# share a single source of truth for the test suite.
_MOCKNET_APP = Path(__file__).resolve().parent.parent / "services" / "mock-network"
if str(_MOCKNET_APP) not in sys.path:
    sys.path.insert(0, str(_MOCKNET_APP))

from app.conformance.kit import TestContext, run  # noqa: E402

# Repo-root schema location (the module's default points at the in-container
# /app/schemas path; on the host we resolve it relative to this script).
DEFAULT_AGENT_FACTS_SCHEMA = (
    Path(__file__).resolve().parent.parent / "schemas" / "agentfacts-v1.json"
)


async def amain(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Conformance test kit for Beckn AI Marketplace BPPs.",
    )
    parser.add_argument("--bpp-url", required=True,
                        help="Base URL of your BPP backend (e.g. https://my-bpp.example.com)")
    parser.add_argument("--bpp-id", required=True,
                        help="Your subscriber id (e.g. acme.ai-providers.com)")
    parser.add_argument("--catalog-path", default="/api/catalog",
                        help="Path to your catalog endpoint (default: /api/catalog)")
    parser.add_argument("--schema", type=Path,
                        help="Override AgentFacts schema path "
                             f"(default: {DEFAULT_AGENT_FACTS_SCHEMA})")
    args = parser.parse_args(argv)

    async with httpx.AsyncClient() as http:
        ctx = TestContext(
            bpp_url=args.bpp_url,
            bpp_id=args.bpp_id,
            catalog_path=args.catalog_path,
            schema_path=args.schema or DEFAULT_AGENT_FACTS_SCHEMA,
            http=http,
        )
        code, _ = await run(ctx, verbose=True)
    return code


def main():
    try:
        sys.exit(asyncio.run(amain(sys.argv[1:])))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
