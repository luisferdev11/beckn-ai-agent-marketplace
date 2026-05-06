"""
Mock catalog of AI agents — provider: Serg Ops.

This catalog complements bpp-provider (General Tecla Industries) and is
designed to coexist on the same network so a single `discover` can return
agents from both providers.

The IDs match those exposed by services/agents-serg/ (the OrderedApi-derived
runtime). Capabilities, inputs, and outputs are written in Beckn v2
JSON-LD style with resourceAttributes following schemas/ai-agents-v1.json.
"""
from __future__ import annotations

PROVIDER = {
    "id": "PROV-SERG-OPS",
    "descriptor": {
        "name": "Serg Ops",
        "shortDesc": "Operational AI agents — drafting, classification, translation, extraction",
    },
    "availableAt": [
        {
            "geo": {"type": "Point", "coordinates": [-99.1332, 19.4326]},
            "address": {
                "streetAddress": "Av. Paseo de la Reforma 200",
                "addressLocality": "Ciudad de México",
                "addressRegion": "CDMX",
                "postalCode": "06600",
                "addressCountry": "MX",
            },
        }
    ],
}


_SCHEMA_CTX = (
    "https://raw.githubusercontent.com/luisferdev11/"
    "beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json"
)


AGENTS = [
    {
        "id": "summarizer-v1",
        "descriptor": {
            "name": "Document Summarizer",
            "shortDesc": "Summarizes long documents into concise bullet points",
            "longDesc": (
                "General-purpose summarization agent. Takes any text input and "
                "returns N bullet points. Useful for reports, articles, and notes."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["document_summary", "text_summary"],
            "languages": ["en", "es"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "100KB"},
            "outputSchema": {"returns": "text/plain"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 5.00},
            "sla": {"maxLatency": "PT3S", "accuracy": 0.93, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
    {
        "id": "extractor-v1",
        "descriptor": {
            "name": "Structured Data Extractor",
            "shortDesc": "Extracts entities (names, dates, amounts) from free text",
            "longDesc": (
                "Parses unstructured text and returns a structured list of the "
                "entities asked for via the `extract` payload field."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["data_extraction", "ner"],
            "languages": ["en", "es"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "100KB"},
            "outputSchema": {"returns": "application/json"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 4.50},
            "sla": {"maxLatency": "PT4S", "accuracy": 0.90, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
    {
        "id": "code-reviewer-v1",
        "descriptor": {
            "name": "Code Reviewer",
            "shortDesc": "Reviews source code for bugs, smells, and best-practices",
            "longDesc": (
                "Pragmatic reviewer that checks correctness and style. Supports "
                "multiple languages via the `language` payload field."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["code_review", "static_analysis"],
            "languages": ["en"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "200KB"},
            "outputSchema": {"returns": "text/plain"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 8.00},
            "sla": {"maxLatency": "PT8S", "accuracy": 0.88, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
    {
        "id": "translator-v1",
        "descriptor": {
            "name": "Translator",
            "shortDesc": "Translates text between supported languages",
            "longDesc": (
                "Translates input text into the language specified in the "
                "`target_lang` payload field."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["translation"],
            "languages": ["en", "es", "fr", "pt"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "50KB"},
            "outputSchema": {"returns": "text/plain"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 3.50},
            "sla": {"maxLatency": "PT3S", "accuracy": 0.92, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
    {
        "id": "email-writer-v1",
        "descriptor": {
            "name": "Email Drafter",
            "shortDesc": "Drafts professional emails from a short brief",
            "longDesc": (
                "Generates a polished email body given a short prompt and an "
                "intended audience or tone."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["text_generation", "email_drafting"],
            "languages": ["en", "es"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "20KB"},
            "outputSchema": {"returns": "text/plain"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 2.50},
            "sla": {"maxLatency": "PT3S", "accuracy": 0.90, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
    {
        "id": "sentiment-v1",
        "descriptor": {
            "name": "Sentiment Analyzer",
            "shortDesc": "Classifies text sentiment as positive / neutral / negative",
            "longDesc": (
                "Lightweight sentiment classifier. Returns label and a short "
                "rationale for the call."
            ),
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _SCHEMA_CTX,
            "@type": "beckn:AIAgentService",
            "capabilities": ["sentiment_analysis", "classification"],
            "languages": ["en", "es"],
            "inputSchema": {"accepts": ["text/plain"], "maxSize": "20KB"},
            "outputSchema": {"returns": "application/json"},
            "pricing": {"model": "per_task", "currency": "MXN", "unitPrice": 2.00},
            "sla": {"maxLatency": "PT2S", "accuracy": 0.91, "uptime": 0.99},
            "dataResidency": "MX",
        },
    },
]


def _make_offer(agent_id: str, name: str) -> dict:
    return {
        "id": f"offer-{agent_id}",
        "descriptor": {"name": name, "shortDesc": f"Standard offer for {agent_id}"},
        "resourceIds": [agent_id],
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "validity": {
            "startDate": "2026-04-01T00:00:00Z",
            "endDate": "2026-12-31T23:59:59Z",
        },
    }


OFFERS = [_make_offer(a["id"], a["descriptor"]["name"]) for a in AGENTS]


def get_catalog_for_publish():
    """Return the catalog payload for Beckn publish and internal use."""
    return {
        "id": "catalog-serg-ops-001",
        "descriptor": {
            "name": "Serg Ops Agent Catalog",
            "shortDesc": "AI agents from Serg Ops — drafting, classification, translation, extraction",
        },
        "provider": PROVIDER,
        "resources": AGENTS,
        "offers": OFFERS,
        "publishDirectives": {"catalogType": "regular"},
    }


def get_agent_by_id(agent_id: str) -> dict | None:
    return next((a for a in AGENTS if a["id"] == agent_id), None)


def get_offer_by_id(offer_id: str) -> dict | None:
    return next((o for o in OFFERS if o["id"] == offer_id), None)
