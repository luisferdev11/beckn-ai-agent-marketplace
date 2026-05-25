#!/usr/bin/env python3
"""Seed the mock-network CDS with synthetic BPPs and AgentFacts catalogs.

Reads a JSON file (default ``infra/mocks/mock_agents_catalog.json``) that
describes 5 themed BPPs plus their AgentFacts agents, then:

  1. Registers (or PATCHes if already registered) each BPP in
     mock-network's subscriber registry.
  2. Publishes each BPP's catalog through ``POST /beckn/catalog/publish``
     so the CDS can index and embed the agents.
  3. Waits a few seconds for the async indexing pipeline to settle, then
     reads ``/cds/stats`` and prints a summary table.

The script is idempotent: re-running it never creates duplicates because
409 conflicts on the registry trigger a PATCH, and the CDS upserts agents
keyed by ``id``.

Usage:
    python infra/mocks/seed_mock_agents.py
    python infra/mocks/seed_mock_agents.py --mocknet-url http://localhost:8090
    python infra/mocks/seed_mock_agents.py --catalog-file path/to/file.json
    python infra/mocks/seed_mock_agents.py --reset   # informational only

Only stdlib + httpx are used (httpx is already a project dependency).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("seed-mock-agents")

# Defaults assume you run the script from the repo root.
DEFAULT_MOCKNET_URL = "http://localhost:8090"
DEFAULT_CATALOG_FILE = "infra/mocks/mock_agents_catalog.json"
HTTP_TIMEOUT = 30.0


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _ensure_subscriber(client: httpx.Client, mocknet_url: str, bpp: dict[str, Any]) -> str:
    """POST the subscriber; on 409 conflict, PATCH the mutable fields."""
    sid = bpp["subscriber_id"]
    create_url = f"{mocknet_url}/registry/subscribers"
    resp = client.post(create_url, json=bpp)
    if resp.status_code == 201:
        logger.info("registered subscriber %s", sid)
        return "created"
    if resp.status_code == 409:
        patch_url = f"{mocknet_url}/registry/subscribers/{sid}"
        # Only send fields the registry will accept as updates.
        patch_body = {
            k: v for k, v in bpp.items()
            if k in {"endpoint_url", "backend_health_url", "organization", "jurisdiction", "public_key"}
        }
        patch_resp = client.patch(patch_url, json=patch_body)
        patch_resp.raise_for_status()
        logger.info("subscriber %s already existed; PATCHed mutable fields", sid)
        return "updated"
    resp.raise_for_status()
    return "unknown"


def _build_publish_envelope(bpp: dict[str, Any], agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Construct a Beckn v2 catalog/publish envelope from a BPP block + agents."""
    sid = bpp["subscriber_id"]
    endpoint = bpp["endpoint_url"]
    org = bpp.get("organization") or {}

    provider_block = {
        "id": sid,
        "descriptor": {
            "name": org.get("name") or sid,
            "shortDesc": org.get("shortDesc") or "",
        },
    }

    resources = []
    offers = []
    for agent in agents:
        desc = agent.get("description") or ""
        resources.append({
            "id": agent["id"],
            "descriptor": {
                "name": agent.get("label") or agent["id"],
                "shortDesc": desc[:200],
                "longDesc": desc,
            },
            "resourceAttributes": agent,
        })
        offers.append({
            "id": f"offer-{agent['id']}",
            "descriptor": {"name": agent.get("label") or agent["id"]},
            "resourceIds": [agent["id"]],
            "provider": provider_block,
        })

    catalog = {
        "id": f"catalog-{sid}",
        "descriptor": {
            "name": org.get("name") or sid,
            "shortDesc": org.get("shortDesc") or f"Catalog for {sid}",
        },
        "provider": provider_block,
        "resources": resources,
        "offers": offers,
    }

    return {
        "context": {
            "networkId": "beckn.one/testnet",
            "action": "catalog/publish",
            "version": "2.0.0",
            "bapId": sid,
            "bapUri": endpoint,
            "bppId": sid,
            "bppUri": endpoint,
            "transactionId": str(uuid.uuid4()),
            "messageId": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "ttl": "PT30S",
        },
        "message": {"catalogs": [catalog]},
    }


def _publish_catalog(client: httpx.Client, mocknet_url: str, envelope: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(f"{mocknet_url}/beckn/catalog/publish", json=envelope)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {}


def _extract_counts(publish_resp: dict[str, Any], total_sent: int) -> tuple[int, int]:
    """Best-effort extraction of accepted/rejected counts from the publish response."""
    msg = publish_resp.get("message") or {}
    ack = msg.get("ack") or {}
    if isinstance(ack, dict) and ack.get("status") == "NACK":
        return 0, total_sent
    accepted = msg.get("accepted")
    rejected = msg.get("rejected")
    if isinstance(accepted, int):
        return accepted, (rejected if isinstance(rejected, int) else total_sent - accepted)
    return total_sent, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mocknet-url", default=DEFAULT_MOCKNET_URL,
                        help=f"Base URL of mock-network (default: {DEFAULT_MOCKNET_URL})")
    parser.add_argument("--catalog-file", default=DEFAULT_CATALOG_FILE,
                        help=f"Path to catalog JSON (default: {DEFAULT_CATALOG_FILE})")
    parser.add_argument("--reset", action="store_true",
                        help="No-op flag for compatibility — script is idempotent via API only.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    catalog_path = Path(args.catalog_file)
    if not catalog_path.is_file():
        logger.error("catalog file not found: %s", catalog_path)
        return 2

    with catalog_path.open() as fh:
        entries = json.load(fh)

    if args.reset:
        logger.info("--reset is informational only: seeding is idempotent via the API.")

    summary: list[tuple[str, str, int, int]] = []
    overall_ok = True

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        for entry in entries:
            bpp = entry["bpp"]
            agents = entry["agents"]
            sid = bpp["subscriber_id"]

            try:
                reg_status = _ensure_subscriber(client, args.mocknet_url, bpp)
            except httpx.HTTPError as exc:
                logger.error("registry call failed for %s: %s", sid, exc)
                summary.append((sid, "registry-failed", 0, len(agents)))
                overall_ok = False
                continue

            envelope = _build_publish_envelope(bpp, agents)
            try:
                publish_resp = _publish_catalog(client, args.mocknet_url, envelope)
            except httpx.HTTPError as exc:
                logger.error("publish failed for %s: %s", sid, exc)
                summary.append((sid, f"publish-failed ({reg_status})", 0, len(agents)))
                overall_ok = False
                continue

            accepted, rejected = _extract_counts(publish_resp, len(agents))
            summary.append((sid, reg_status, accepted, rejected))
            logger.info("published %s: accepted=%d rejected=%d", sid, accepted, rejected)

        # Give the async background indexer time to embed + persist.
        time.sleep(3)

        try:
            stats_resp = client.get(f"{args.mocknet_url}/cds/stats")
            stats = stats_resp.json() if stats_resp.status_code == 200 else {}
        except httpx.HTTPError:
            stats = {}

    print()
    print("=" * 78)
    print(f"{'BPP':<35} {'Registry':<18} {'Accepted':>10} {'Rejected':>10}")
    print("-" * 78)
    for sid, reg, ok, ko in summary:
        print(f"{sid:<35} {reg:<18} {ok:>10} {ko:>10}")
    print("=" * 78)
    if stats:
        total_agents = stats.get("total_agents") or stats.get("agents") or stats.get("agent_count")
        if total_agents is not None:
            print(f"CDS reports total indexed agents: {total_agents}")
        else:
            print(f"CDS /cds/stats response: {json.dumps(stats)}")
    else:
        print("CDS /cds/stats unavailable; seeding step completed.")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
