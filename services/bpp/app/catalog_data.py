"""
Mock catalog of AI agents for Iter 0.

This hardcoded catalog will be replaced by a database-backed catalog
in future iterations. For now it provides 3 agents with realistic
attributes using the AgentFacts schema (projnanda/agentfacts-format).

Each agent has:
- Beckn descriptor (name, description)
- resourceAttributes following AgentFacts v1 (id, agent_name, skills, sla, ...)
  plus a non-standard `pricing` field read by handle_select()
- An offer with validity dates
"""
from __future__ import annotations

PROVIDER = {
    "id": "PROV-AI-001",
    "descriptor": {
        "name": "AI Solutions Demo Provider",
        "shortDesc": "Demo provider of AI agents for the Beckn marketplace",
    },
    "availableAt": [
        {
            "geo": {"type": "Point", "coordinates": [77.6401, 12.9116]},
            "address": {
                "streetAddress": "27th Main Rd, HSR Layout",
                "addressLocality": "Bengaluru",
                "addressRegion": "Karnataka",
                "postalCode": "560102",
                "addressCountry": "IN",
            },
        }
    ],
}

_AGENTFACTS_CONTEXT = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json"
_PROVIDER_URL = "http://bpp-provider:3002"
_BPP_ENDPOINT = "http://onix-bpp:8082/bpp/caller"

AGENTS = [
    {
        "id": "agent-summarizer-001",
        "descriptor": {
            "name": "Legal Document Summarizer",
            "shortDesc": "Summarizes legal and regulatory documents in Hindi and English",
            "longDesc": "An AI agent specialized in analyzing legal documents, contracts, "
            "and regulatory filings. Produces structured summaries with key provisions, "
            "obligations, and risk factors identified.",
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _AGENTFACTS_CONTEXT,
            "id": "beckn-marketplace:summarizer-v1",
            "agent_name": "urn:agent:beckn-marketplace:LegalDocumentSummarizer",
            "label": "Legal Document Summarizer",
            "description": "Summarizes legal and regulatory documents in Hindi and English",
            "version": "1.0.0",
            "jurisdiction": "IN",
            "provider": {"name": PROVIDER["descriptor"]["name"], "url": _PROVIDER_URL},
            "endpoints": {"static": [_BPP_ENDPOINT]},
            "capabilities": {
                "modalities": ["text"],
                "streaming": False,
                "batch": False,
                "authentication": {"methods": ["jwt"]},
            },
            "skills": [
                {
                    "id": "document_summary",
                    "description": "Summarizes legal and regulatory documents",
                    "inputModes": ["text/plain", "application/pdf"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en", "hi"],
                    "latencyBudgetMs": 5000,
                    "maxTokens": 4096,
                },
                {
                    "id": "legal_analysis",
                    "description": "Analyzes legal clauses and provisions",
                    "inputModes": ["text/plain"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en", "hi"],
                    "latencyBudgetMs": 5000,
                },
            ],
            "sla": {"maxLatencyMs": 5000, "accuracy": 0.95, "uptime": 0.995},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 6.00},
        },
    },
    {
        "id": "agent-code-reviewer-001",
        "descriptor": {
            "name": "Code Review Assistant",
            "shortDesc": "Reviews code for bugs, security issues, and best practices",
            "longDesc": "An AI agent that performs automated code review. Analyzes code "
            "for common vulnerabilities (OWASP Top 10), performance issues, and adherence "
            "to coding standards. Supports Python, JavaScript, TypeScript, Go, and Java.",
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _AGENTFACTS_CONTEXT,
            "id": "beckn-marketplace:code-reviewer-v1",
            "agent_name": "urn:agent:beckn-marketplace:CodeReviewAssistant",
            "label": "Code Review Assistant",
            "description": "Reviews code for bugs, security issues, and best practices",
            "version": "1.0.0",
            "jurisdiction": "IN",
            "provider": {"name": PROVIDER["descriptor"]["name"], "url": _PROVIDER_URL},
            "endpoints": {"static": [_BPP_ENDPOINT]},
            "capabilities": {
                "modalities": ["text"],
                "streaming": False,
                "batch": False,
                "authentication": {"methods": ["jwt"]},
            },
            "skills": [
                {
                    "id": "code_review",
                    "description": "Reviews code for bugs and quality issues",
                    "inputModes": ["text/plain", "application/zip"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en"],
                    "latencyBudgetMs": 30000,
                    "maxTokens": 8192,
                },
                {
                    "id": "security_analysis",
                    "description": "Detects OWASP Top 10 vulnerabilities",
                    "inputModes": ["text/plain"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en"],
                    "latencyBudgetMs": 30000,
                },
                {
                    "id": "best_practices",
                    "description": "Checks adherence to coding standards",
                    "inputModes": ["text/plain"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en"],
                    "latencyBudgetMs": 30000,
                },
            ],
            "sla": {"maxLatencyMs": 30000, "accuracy": 0.90, "uptime": 0.99},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 10.00},
        },
    },
    {
        "id": "agent-data-extractor-001",
        "descriptor": {
            "name": "Invoice Data Extractor",
            "shortDesc": "Extracts structured data from invoices and financial documents",
            "longDesc": "An AI agent that processes scanned invoices, receipts, and "
            "financial documents to extract structured data: line items, amounts, dates, "
            "vendor information, and tax details. Returns standardized JSON output.",
        },
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "availableAt": PROVIDER["availableAt"],
        "resourceAttributes": {
            "@context": _AGENTFACTS_CONTEXT,
            "id": "beckn-marketplace:data-extractor-v1",
            "agent_name": "urn:agent:beckn-marketplace:InvoiceDataExtractor",
            "label": "Invoice Data Extractor",
            "description": "Extracts structured data from invoices and financial documents",
            "version": "1.0.0",
            "jurisdiction": "IN",
            "provider": {"name": PROVIDER["descriptor"]["name"], "url": _PROVIDER_URL},
            "endpoints": {"static": [_BPP_ENDPOINT]},
            "capabilities": {
                "modalities": ["text", "image"],
                "streaming": False,
                "batch": True,
                "authentication": {"methods": ["jwt"]},
            },
            "skills": [
                {
                    "id": "data_extraction",
                    "description": "Extracts structured fields from financial documents",
                    "inputModes": ["image/jpeg", "image/png", "application/pdf"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en", "hi", "ta"],
                    "latencyBudgetMs": 10000,
                    "maxTokens": 4096,
                },
                {
                    "id": "ocr",
                    "description": "Optical character recognition for scanned documents",
                    "inputModes": ["image/jpeg", "image/png"],
                    "outputModes": ["text/plain"],
                    "supportedLanguages": ["en", "hi", "ta"],
                    "latencyBudgetMs": 5000,
                },
                {
                    "id": "invoice_processing",
                    "description": "Parses invoice line items, totals, and vendor details",
                    "inputModes": ["application/pdf", "image/jpeg", "image/png"],
                    "outputModes": ["application/json"],
                    "supportedLanguages": ["en", "hi"],
                    "latencyBudgetMs": 10000,
                },
            ],
            "sla": {"maxLatencyMs": 10000, "accuracy": 0.92, "uptime": 0.995},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 4.00},
        },
    },
]

OFFERS = [
    {
        "id": "offer-summarizer-basic",
        "descriptor": {
            "name": "Basic Summarization",
            "shortDesc": "Single document summarization",
        },
        "resourceIds": ["agent-summarizer-001"],
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "validity": {
            "startDate": "2026-04-01T00:00:00Z",
            "endDate": "2026-12-31T23:59:59Z",
        },
    },
    {
        "id": "offer-code-review-basic",
        "descriptor": {
            "name": "Basic Code Review",
            "shortDesc": "Single repository code review",
        },
        "resourceIds": ["agent-code-reviewer-001"],
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "validity": {
            "startDate": "2026-04-01T00:00:00Z",
            "endDate": "2026-12-31T23:59:59Z",
        },
    },
    {
        "id": "offer-data-extractor-basic",
        "descriptor": {
            "name": "Basic Data Extraction",
            "shortDesc": "Single document data extraction",
        },
        "resourceIds": ["agent-data-extractor-001"],
        "provider": {"id": PROVIDER["id"], "descriptor": PROVIDER["descriptor"]},
        "validity": {
            "startDate": "2026-04-01T00:00:00Z",
            "endDate": "2026-12-31T23:59:59Z",
        },
    },
]


def get_catalog_for_publish():
    """Return the catalog payload for Beckn publish and internal use."""
    return {
        "id": "catalog-ai-agents-001",
        "descriptor": {
            "name": "AI Agent Catalog",
            "shortDesc": "Catalog of AI agents for document processing, code review, and data extraction",
        },
        "provider": PROVIDER,
        "resources": AGENTS,
        "offers": OFFERS,
        "publishDirectives": {"catalogType": "regular"},
    }


def get_agent_by_id(agent_id: str) -> dict | None:
    """Find an agent by its resource ID."""
    for agent in AGENTS:
        if agent["id"] == agent_id:
            return agent
    return None


def get_offer_by_id(offer_id: str) -> dict | None:
    """Find an offer by its ID."""
    for offer in OFFERS:
        if offer["id"] == offer_id:
            return offer
    return None
