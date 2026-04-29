"""
Agent and offer factories for BPP tests.

Build catalog entries for testing without depending on catalog_data.py hardcoded values.
Tests that use these factories remain valid even when the catalog changes.
"""


def make_agent(
    agent_id: str = "agent-test-001",
    name: str = "Test Agent",
    unit_price: float = 5.0,
    capabilities: list = None,
    max_latency_ms: int = 10000,
) -> dict:
    schema_url = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json"
    skill_ids = capabilities or ["test_capability"]
    return {
        "id": agent_id,
        "descriptor": {
            "name": name,
            "shortDesc": f"Test agent: {name}",
        },
        "provider": {"id": "PROV-TEST-001", "descriptor": {"name": "Test Provider"}},
        "resourceAttributes": {
            "@context": schema_url,
            "id": f"test:{agent_id}",
            "agent_name": f"urn:agent:test:{name.replace(' ', '')}",
            "label": name,
            "description": f"Test agent: {name}",
            "version": "1.0.0",
            "jurisdiction": "IN",
            "provider": {"name": "Test Provider", "url": "http://bpp-provider:3002"},
            "endpoints": {"static": ["http://onix-bpp:8082/bpp/caller"]},
            "capabilities": {
                "modalities": ["text"],
                "streaming": False,
                "batch": False,
                "authentication": {"methods": ["jwt"]},
            },
            "skills": [
                {
                    "id": sid,
                    "description": f"Test skill: {sid}",
                    "inputModes": ["text/plain"],
                    "outputModes": ["application/json"],
                    "latencyBudgetMs": max_latency_ms,
                }
                for sid in skill_ids
            ],
            "sla": {"maxLatencyMs": max_latency_ms, "accuracy": 0.90, "uptime": 0.99},
            "pricing": {"model": "per_task", "currency": "INR", "unitPrice": unit_price},
        },
    }


def make_offer(offer_id: str = "offer-test-basic", agent_id: str = "agent-test-001") -> dict:
    return {
        "id": offer_id,
        "descriptor": {"name": "Test Offer", "shortDesc": "Test offer"},
        "resourceIds": [agent_id],
        "provider": {"id": "PROV-TEST-001", "descriptor": {"name": "Test Provider"}},
        "validity": {"startDate": "2026-01-01T00:00:00Z", "endDate": "2026-12-31T23:59:59Z"},
    }


def make_select_contract_message(
    agent_id: str = "agent-summarizer-001",
    offer_id: str = "offer-summarizer-basic",
    quantity: int = 1,
    txn_id: str = "test-txn-001",
) -> dict:
    return {
        "contract": {
            "id": f"contract-{txn_id[:8]}",
            "participants": [
                {"id": "participant-buyer-001", "descriptor": {"name": "Test User", "code": "buyer"}}
            ],
            "commitments": [{
                "id": "commitment-001",
                "descriptor": {"name": "AI Agent Service", "code": "AAS-001"},
                "status": {"code": "DRAFT"},
                "resources": [{
                    "id": agent_id,
                    "descriptor": {"name": "AI Agent", "code": agent_id},
                    "quantity": {"unitQuantity": quantity, "unitCode": "UNIT"},
                }],
                "offer": {"id": offer_id, "resourceIds": [agent_id]},
            }],
        }
    }


def make_beckn_context(action: str, txn_id: str = "test-txn-001") -> dict:
    import uuid
    return {
        "networkId": "beckn.one/testnet",
        "action": action,
        "version": "2.0.0",
        "bapId": "bap.example.com",
        "bapUri": "http://onix-bap:8081/bap/receiver",
        "bppId": "bpp.example.com",
        "bppUri": "http://onix-bpp:8082/bpp/receiver",
        "transactionId": txn_id,
        "messageId": str(uuid.uuid4()),
        "timestamp": "2026-04-22T00:00:00.000Z",
        "ttl": "PT30S",
    }
