"""
Beckn message factories.

Build valid Beckn v2 payloads for tests. Use these instead of hardcoding
dicts in every test — when the protocol changes, update here only.
"""

import uuid
from datetime import datetime, timezone


def make_context(action: str, txn_id: str = None, **overrides) -> dict:
    ctx = {
        "networkId": "beckn.one/testnet",
        "action": action,
        "version": "2.0.0",
        "bapId": "bap.example.com",
        "bapUri": "http://onix-bap:8081/bap/receiver",
        "bppId": "bpp.example.com",
        "bppUri": "http://onix-bpp:8082/bpp/receiver",
        "transactionId": txn_id or str(uuid.uuid4()),
        "messageId": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "ttl": "PT30S",
    }
    ctx.update(overrides)
    return ctx


def make_select_payload(
    agent_id: str = "agent-summarizer-001",
    offer_id: str = "offer-summarizer-basic",
    quantity: int = 1,
    txn_id: str = None,
    buyer_name: str = "Test User",
) -> dict:
    return {
        "agent_id": agent_id,
        "offer_id": offer_id,
        "quantity": quantity,
        "transaction_id": txn_id,
        "buyer_name": buyer_name,
    }


def make_on_select_callback(
    txn_id: str,
    contract_id: str = None,
    agent_id: str = "agent-summarizer-001",
    price_value: str = "7.08",
) -> dict:
    cid = contract_id or f"contract-{txn_id[:8]}"
    return {
        "context": make_context("on_select", txn_id=txn_id),
        "message": {
            "contract": {
                "id": cid,
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
                        "quantity": {"unitQuantity": 1, "unitCode": "UNIT"},
                    }],
                    "offer": {"id": "offer-summarizer-basic", "resourceIds": [agent_id]},
                }],
                "consideration": [{
                    "id": "consideration-commitment-001",
                    "price": {"currency": "INR", "value": price_value},
                    "status": {"code": "DRAFT"},
                    "breakup": [
                        {"title": "AI Agent x1", "price": {"currency": "INR", "value": "6.00"}},
                        {"title": "GST (18%)", "price": {"currency": "INR", "value": "1.08"}},
                    ],
                }],
            }
        },
    }


def make_on_confirm_callback(txn_id: str, contract_id: str = None) -> dict:
    cid = contract_id or f"contract-{txn_id[:8]}"
    return {
        "context": make_context("on_confirm", txn_id=txn_id),
        "message": {
            "contract": {
                "id": cid,
                "commitments": [{"id": "commitment-001", "status": {"code": "ACTIVE"}}],
                "performance": [{"id": "perf-001", "status": {"code": "RUNNING"}}],
                "settlements": [{"id": "settlement-001", "status": "COMPLETE"}],
            }
        },
    }


def make_on_status_completed_callback(txn_id: str, contract_id: str = None) -> dict:
    cid = contract_id or f"contract-{txn_id[:8]}"
    schema_url = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/execution-result-v1.json"
    return {
        "context": make_context("on_status", txn_id=txn_id),
        "message": {
            "contract": {
                "id": cid,
                "commitments": [{"id": "commitment-001", "status": {"code": "ACTIVE"}}],
                "performance": [{
                    "id": "perf-001",
                    "status": {"code": "COMPLETED", "name": "Completed", "shortDesc": "Done"},
                    "performanceAttributes": {
                        "@context": schema_url,
                        "@type": "beckn:AgentExecution",
                        "startedAt": "2026-04-22T00:00:00.000Z",
                        "completedAt": "2026-04-22T00:00:01.500Z",
                        "latencyMs": 1500,
                        "tokensUsed": {"input": 109, "output": 523, "total": 632},
                        "model": "llama-3.3-70b-versatile",
                        "result": {"review": "Code looks good."},
                        "status": "COMPLETED",
                    },
                }],
            }
        },
    }
