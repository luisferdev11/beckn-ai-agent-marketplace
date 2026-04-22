"""
Mock catalog of AI agents for Iter 0.

This hardcoded catalog will be replaced by a database-backed catalog
in future iterations. For now it provides 3 agents with realistic
attributes using the beckn:AIAgentService JSON-LD schema.

Each agent has:
- Beckn descriptor (name, description)
- resourceAttributes with AI-specific fields (capabilities, SLA, pricing)
- An offer with pricing
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
            "@context": "https://raw.githubusercontent.com/luisferdev11/beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json",
            "@type": "beckn:AIAgentService",
            "capabilities": ["document_summary", "legal_analysis"],
            "languages": ["en", "hi"],
            "inputSchema": {"accepts": ["application/pdf", "text/plain"], "maxSize": "50MB"},
            "outputSchema": {"returns": "application/json"},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 6.00},
            "sla": {"maxLatency": "PT5S", "accuracy": 0.95, "uptime": 0.995},
            "dataResidency": "IN",
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
            "@context": "https://raw.githubusercontent.com/luisferdev11/beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json",
            "@type": "beckn:AIAgentService",
            "capabilities": ["code_review", "security_analysis", "best_practices"],
            "languages": ["en"],
            "inputSchema": {
                "accepts": ["text/plain", "application/zip"],
                "maxSize": "100MB",
            },
            "outputSchema": {"returns": "application/json"},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 10.00},
            "sla": {"maxLatency": "PT30S", "accuracy": 0.90, "uptime": 0.99},
            "dataResidency": "IN",
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
            "@context": "https://raw.githubusercontent.com/luisferdev11/beckn-ai-agent-marketplace/main/schemas/ai-agents-v1.json",
            "@type": "beckn:AIAgentService",
            "capabilities": ["data_extraction", "ocr", "invoice_processing"],
            "languages": ["en", "hi", "ta"],
            "inputSchema": {
                "accepts": ["image/jpeg", "image/png", "application/pdf"],
                "maxSize": "20MB",
            },
            "outputSchema": {"returns": "application/json"},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": 4.00},
            "sla": {"maxLatency": "PT10S", "accuracy": 0.92, "uptime": 0.995},
            "dataResidency": "IN",
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
