"""BPP-Serg catalog publish to the CDS.

⚠ DEMO-ONLY ADAPTER — NOT A PRODUCTION PATTERN ⚠

Serg's in-memory catalog (``app.catalog_data.AGENTS``) uses a LEGACY
resourceAttributes shape (capabilities as a flat array, dataResidency,
ISO-duration latency, ...). The marketplace's CDS expects AgentFacts v1
and rejects anything else.

In a real-world integration the BPP author would migrate their catalog
to produce AgentFacts directly — that is the responsibility line. The
transformer in ``_to_agent_facts`` exists ONLY because Serg is an
internal demo BPP that we did not want to rewrite during the discover-v2
rollout. It SHOULD NOT be replicated by external BPPs.

How to handle this in your own BPP:
  - Author your catalog as AgentFacts v1 from the start. See
    ``services/bpp/app/routes/provider_api.py:_agent_to_beckn_resource``
    for the canonical example.
  - The CDS will validate every item and reject non-compliant ones with
    a per-item error in ``on_publish.results[].errors``.

When Serg eventually migrates its catalog to AgentFacts v1, this
transformer collapses to a straight POST. Remove it then.

Endpoint: POST /api/publish
  - Builds a Beckn v2 catalog/publish envelope.
  - POSTs through ONIX-BPP-Serg's caller (which signs + routes to CDS).
  - CDS responds ACK synchronously, on_publish callback arrives at
    /api/webhook/on_publish.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from app.catalog_data import AGENTS, PROVIDER
from app.config import BPP_CALLBACK_URL, BPP_ID, BPP_URI, NETWORK_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["provider-portal"])


# ─── ISO-8601 duration → milliseconds helper ─────────────────────


_ISO_DURATION_RE = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def _iso_duration_to_ms(value) -> int | None:
    if not isinstance(value, str):
        return None
    match = _ISO_DURATION_RE.match(value)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0.0)
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return int(total_seconds * 1000)


# ─── Legacy → AgentFacts v1 transformer ──────────────────────────


def _camel_case(text: str) -> str:
    """Turn a free-form name into a URN-safe CamelCase token."""
    parts = re.split(r"[^A-Za-z0-9]+", text or "")
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Agent"


def _version_from_id(agent_id: str) -> str:
    """Pull a semver out of an id like ``summarizer-v1`` → ``1.0.0``.
    Defaults to 1.0.0 when no -vN suffix is present.
    """
    match = re.search(r"-v(\d+)$", agent_id or "")
    if match:
        return f"{match.group(1)}.0.0"
    return "1.0.0"


def _to_agent_facts(agent: dict) -> dict:
    """Map a Serg legacy catalog entry into an AgentFacts v1 document."""
    legacy = agent.get("resourceAttributes") or {}
    descriptor = agent.get("descriptor") or {}
    label = descriptor.get("name") or "AI Agent"
    description = descriptor.get("longDesc") or descriptor.get("shortDesc") or ""

    languages = legacy.get("languages") or []
    capabilities_list = legacy.get("capabilities") or []
    input_modes = (legacy.get("inputSchema") or {}).get("accepts") or ["text/plain"]
    output_returns = (legacy.get("outputSchema") or {}).get("returns") or "text/plain"
    output_modes = [output_returns] if isinstance(output_returns, str) else list(output_returns)

    skills = [
        {
            "id": cap,
            "description": (
                descriptor.get("shortDesc")
                or f"{label} skill {cap.replace('_', ' ')}"
            ),
            "inputModes": list(input_modes),
            "outputModes": list(output_modes),
            "supportedLanguages": list(languages),
        }
        for cap in capabilities_list
    ]
    if not skills:
        # Defensive: every AgentFacts payload must declare at least one
        # skill per the schema (minItems: 1).
        skills = [{
            "id": "general",
            "description": description or label,
            "inputModes": list(input_modes),
            "outputModes": list(output_modes),
            "supportedLanguages": list(languages),
        }]

    sla_legacy = legacy.get("sla") or {}
    sla = {}
    max_latency_ms = _iso_duration_to_ms(sla_legacy.get("maxLatency"))
    if max_latency_ms is not None:
        sla["maxLatencyMs"] = max_latency_ms
    if isinstance(sla_legacy.get("accuracy"), (int, float)):
        sla["accuracy"] = float(sla_legacy["accuracy"])
    if isinstance(sla_legacy.get("uptime"), (int, float)):
        sla["uptime"] = float(sla_legacy["uptime"])

    pricing_legacy = legacy.get("pricing") or {}
    pricing = {}
    if pricing_legacy.get("currency"):
        pricing["currency"] = pricing_legacy["currency"]
    unit = pricing_legacy.get("unitPrice") or pricing_legacy.get("value")
    if unit is not None:
        pricing["value"] = float(unit)
    if pricing_legacy.get("model"):
        pricing["model"] = pricing_legacy["model"]

    facts: dict = {
        "@context": "https://raw.githubusercontent.com/i-interns/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json",
        "@type": "beckn:AIAgentService",
        "id": f"serg-ops:{agent['id']}",
        "agent_name": f"urn:agent:serg-ops:{_camel_case(label)}",
        "label": label,
        "description": description,
        "version": _version_from_id(agent["id"]),
        "jurisdiction": "MEX",
        "provider": {
            "name": (PROVIDER.get("descriptor") or {}).get("name") or "Serg Ops",
            "url": "http://bpp-serg:3005",
        },
        "endpoints": {"static": [BPP_URI]},
        "capabilities": {
            "modalities": ["text"],
            "streaming": False,
            "batch": False,
            "authentication": {"methods": ["jwt"]},
        },
        "skills": skills,
    }
    if sla:
        facts["sla"] = sla
    if pricing:
        facts["pricing"] = pricing

    # Carry through real JSON Schema contracts when present. The CDS
    # requires non-empty inputSchema/outputSchema dicts to accept an
    # agent in strict mode (pipeline eligibility).
    for schema_key in ("inputSchema", "outputSchema"):
        schema = legacy.get(schema_key)
        if isinstance(schema, dict) and schema.get("type"):
            facts[schema_key] = schema

    return facts


# ─── Beckn envelope assembly ─────────────────────────────────────


def _build_provider_block() -> dict:
    desc = PROVIDER.get("descriptor") or {}
    return {
        "id": BPP_ID,
        "descriptor": {
            "name": desc.get("name") or BPP_ID,
            "shortDesc": desc.get("shortDesc") or "",
        },
    }


@router.post("/publish")
async def publish_catalog():
    """Publish Serg's catalog to the CDS through ONIX-BPP-Serg."""
    provider_block = _build_provider_block()
    resources = []
    offers = []
    for agent in AGENTS:
        facts = _to_agent_facts(agent)
        descriptor = agent.get("descriptor") or {}
        resources.append({
            "id": agent["id"],
            "descriptor": {
                "name": descriptor.get("name") or "Agent",
                "shortDesc": descriptor.get("shortDesc") or "",
                "longDesc": descriptor.get("longDesc") or "",
            },
            "resourceAttributes": facts,
        })
        offers.append({
            "id": f"offer-{agent['id']}",
            "descriptor": {"name": descriptor.get("name") or agent["id"]},
            "resourceIds": [agent["id"]],
            "provider": provider_block,
        })

    catalog = {
        "id": f"catalog-{BPP_ID}",
        "descriptor": {
            "name": f"{provider_block['descriptor']['name']} — AI Agents",
            "shortDesc": f"Catalog with {len(resources)} AI agents",
        },
        "provider": provider_block,
        "resources": resources,
        "offers": offers,
    }

    dt = datetime.now(timezone.utc)
    timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    txn_id = str(uuid.uuid4())

    payload = {
        "context": {
            "networkId": NETWORK_ID,
            "action": "catalog/publish",
            "version": "2.0.0",
            # publish has no buyer counterparty; reuse bppId to satisfy
            # context validation.
            "bapId": BPP_ID,
            "bapUri": BPP_URI,
            "bppId": BPP_ID,
            "bppUri": BPP_URI,
            "transactionId": txn_id,
            "messageId": str(uuid.uuid4()),
            "timestamp": timestamp,
            "ttl": "PT30S",
        },
        "message": {"catalogs": [catalog]},
    }

    publish_url = f"{BPP_CALLBACK_URL}/publish"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(publish_url, json=payload)
        ok = response.status_code == 200
        ack_status = "?"
        try:
            ack_status = (response.json().get("message") or {}).get("ack", {}).get("status", "?")
        except Exception:
            pass
        logger.info(
            "publish sent to CDS — HTTP %d ack=%s [%d agents] [txn=%s]",
            response.status_code, ack_status, len(resources), txn_id[:8],
        )
        return {
            "status": "sent",
            "fabric": {
                "catalogPublished": ok,
                "ack": ack_status,
                "agentsInCatalog": len(resources),
            },
            "transactionId": txn_id,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(f"publish failed: {exc}")
        return {"status": "error", "detail": str(exc)}
