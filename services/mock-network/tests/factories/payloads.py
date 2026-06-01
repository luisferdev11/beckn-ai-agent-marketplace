"""Builders for AgentFacts and Beckn publish payloads.

Used by route + service tests. Each builder accepts overrides as kwargs
so tests can mutate the bit they care about without re-typing the
entire structure.
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ── AgentFacts ─────────────────────────────────────────────────────


def valid_agent_facts(**overrides) -> dict:
    """A minimally-valid AgentFacts payload (passes the v1 schema)."""
    base = {
        "@context": "https://example.com/schemas/agentfacts-v1.json",
        "@type": "beckn:AIAgentService",
        "id": "marketplace:summarizer-v1",
        "agent_name": "urn:agent:marketplace:DocumentSummarizer",
        "label": "Document Summarizer",
        "description": "Summarises legal documents in Hindi and English.",
        "version": "1.0.0",
        "jurisdiction": "IND",
        "provider": {
            "name": "General Tecla Industries",
            "url": "http://bpp-provider:3002",
        },
        "endpoints": {
            "static": ["http://onix-bpp:8082/bpp/receiver"],
        },
        "capabilities": {
            "modalities": ["text"],
            "streaming": False,
            "batch": False,
            "authentication": {"methods": ["jwt"]},
        },
        "skills": [
            {
                "id": "document_summary",
                "description": "Summarises legal and regulatory documents.",
                "inputModes": ["text/plain", "application/pdf"],
                "outputModes": ["application/json"],
                "supportedLanguages": ["en", "hi"],
                "latencyBudgetMs": 5000,
            },
        ],
        "sla": {
            "maxLatencyMs": 5000,
            "uptime": 0.995,
        },
        "pricing": {
            "currency": "INR",
            "value": 6.0,
        },
        # Rigorous input/output schema contracts (Epic D). A "valid" agent
        # in a marketplace that requires schemas must declare both.
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    }
    base.update(overrides)
    return base


def agent_facts_missing(field: str) -> dict:
    """An AgentFacts payload with the named required field removed."""
    af = valid_agent_facts()
    af.pop(field, None)
    return af


def agent_facts_without_schemas() -> dict:
    """A structurally-valid AgentFacts payload lacking the input/output
    schema contracts — rejected under strict mode (Epic D)."""
    af = valid_agent_facts()
    af.pop("inputSchema", None)
    af.pop("outputSchema", None)
    return af


def agent_facts_bad_version() -> dict:
    af = valid_agent_facts()
    af["version"] = "not-semver"
    return af


# ── Beckn publish envelope ─────────────────────────────────────────


def beckn_resource(agent_facts: dict, resource_id: str | None = None) -> dict:
    rid = resource_id or "agent-summarizer-001"
    return {
        "id": rid,
        "descriptor": {
            "name": agent_facts.get("label", "Agent"),
            "shortDesc": (agent_facts.get("description") or "")[:200],
        },
        "resourceAttributes": deepcopy(agent_facts),
    }


def beckn_catalog(resources: list[dict], provider_id: str = "1") -> dict:
    return {
        "id": "catalog-test-001",
        "descriptor": {"name": "AI Agent Catalog"},
        "provider": {
            "id": provider_id,
            "descriptor": {"name": "General Tecla Industries"},
        },
        "resources": resources,
    }


def publish_envelope(
    catalogs: list[dict] | None = None,
    *,
    bpp_id: str = "bpp.example.com",
    bpp_uri: str = "http://onix-bpp:8082/bpp/receiver",
    transaction_id: str | None = None,
) -> dict:
    """Build the full Beckn v2 envelope a BPP would POST to catalog/publish.

    Default content: one catalog with one valid resource — enough for the
    happy-path route test. Override by passing ``catalogs=...``.
    """
    if catalogs is None:
        catalogs = [beckn_catalog([beckn_resource(valid_agent_facts())])]
    return {
        "context": {
            "networkId": "beckn.one/testnet",
            "action": "catalog/publish",
            "version": "2.0.0",
            "bapId": bpp_id,  # publish has bpp == originator
            "bapUri": bpp_uri,
            "bppId": bpp_id,
            "bppUri": bpp_uri,
            "transactionId": transaction_id or str(uuid.uuid4()),
            "messageId": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "ttl": "PT30S",
        },
        "message": {"catalogs": catalogs},
    }
