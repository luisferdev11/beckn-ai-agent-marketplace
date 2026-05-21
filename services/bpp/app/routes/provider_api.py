"""BPP Provider API — CRUD endpoints for categories, providers, agents, publish."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.config import BPP_CALLBACK_URL, BPP_ID, BPP_URI, NETWORK_ID
from app.db import repository as repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["provider-portal"])


# ─── Categories ──────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    display_name: dict = {}
    description: Optional[str] = None


@router.post("/categories", status_code=201)
async def create_category(req: CategoryCreate):
    cat = await repo.create_category(req.name, req.display_name, req.description)
    return {"category_id": cat["id"], "category": cat}


@router.get("/categories")
async def list_categories():
    return await repo.list_categories()


# ─── Providers ───────────────────────────────────────────────

class ProviderCreate(BaseModel):
    subscriber_id: str
    bpp_uri: str
    public_key: Optional[str] = None
    organization_details: dict = {}


@router.post("/providers", status_code=201)
async def create_provider(req: ProviderCreate):
    prov = await repo.create_provider(
        req.subscriber_id, req.bpp_uri, req.public_key, req.organization_details,
    )
    return {"provider": prov}


@router.get("/providers")
async def list_providers():
    return await repo.list_providers()


# ─── Agents ──────────────────────────────────────────────────

class AgentCreate(BaseModel):
    provider_id: int
    category_id: int
    agent_name: dict = {}
    beckn_id: Optional[str] = None
    agentfacts_id: Optional[str] = None
    agent_urn: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    access_point_url: Optional[str] = None
    interaction_type: str = "sync"
    version: str = "1.0.0"
    capabilities: dict = {}
    skills: list = []
    input_schema: dict = {}
    output_schema: dict = {}
    model_provider: Optional[str] = None
    pricing_model: dict = {}
    sla: dict = {}
    jurisdiction: Optional[str] = None
    endpoints: Optional[dict] = None


@router.post("/agents", status_code=201)
async def create_agent(req: AgentCreate):
    agent = await repo.create_agent(
        provider_id=req.provider_id,
        category_id=req.category_id,
        agent_name=req.agent_name,
        beckn_id=req.beckn_id,
        agentfacts_id=req.agentfacts_id,
        agent_urn=req.agent_urn,
        label=req.label,
        description=req.description,
        access_point_url=req.access_point_url,
        interaction_type=req.interaction_type,
        version=req.version,
        capabilities=req.capabilities,
        skills=req.skills,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
        model_provider=req.model_provider,
        pricing_model=req.pricing_model,
        sla=req.sla,
        jurisdiction=req.jurisdiction,
        endpoints=req.endpoints,
    )
    return {"agent_id": agent["id"], "agent": agent}


class AgentUpdate(BaseModel):
    version: Optional[str] = None
    model_provider: Optional[str] = None
    pricing_model: Optional[dict] = None
    capabilities: Optional[dict] = None
    skills: Optional[list] = None
    sla: Optional[dict] = None
    description: Optional[str] = None
    access_point_url: Optional[str] = None
    interaction_type: Optional[str] = None
    label: Optional[str] = None
    agent_urn: Optional[str] = None


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: int, req: AgentUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    agent = await repo.update_agent(agent_id, **updates)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.delete("/agents/{agent_id}")
async def deactivate_agent(agent_id: int):
    result = await repo.deactivate_agent(agent_id)
    if not result:
        raise HTTPException(404, "Agent not found")
    return {"message": "Agent deactivated", "agent_id": agent_id}


@router.get("/agents")
async def list_agents():
    return await repo.list_agents()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: int):
    agent = await repo.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


# ─── Publish ─────────────────────────────────────────────────

def _parse_jsonb(val, default=None):
    if isinstance(val, str):
        return json.loads(val)
    if val is None:
        return default
    return val


def _agent_to_beckn_resource(agent: dict) -> dict:
    """Convert a DB agent row to a Beckn v2 catalog resource with AgentFacts."""
    label = agent.get("label") or "AI Agent"
    caps = _parse_jsonb(agent["capabilities"], default={})
    skills = _parse_jsonb(agent["skills"], default=[])
    input_schema = _parse_jsonb(agent["input_schema"], default={})
    output_schema = _parse_jsonb(agent["output_schema"], default={})
    pricing = _parse_jsonb(agent["pricing_model"], default={})
    sla = _parse_jsonb(agent["sla"], default={})
    endpoints = _parse_jsonb(agent["endpoints"], default={"static": []})
    provider_org = _parse_jsonb(agent.get("provider_org"), default={})

    schema_url = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json"

    return {
        "id": agent["beckn_id"] or str(agent["id"]),
        "descriptor": {
            "name": label,
            "shortDesc": (agent.get("description") or "")[:200],
            "longDesc": agent.get("description") or "",
        },
        "resourceAttributes": {
            "@context": schema_url,
            "@type": "beckn:AIAgentService",
            "id": agent.get("agentfacts_id") or f"marketplace:agent-{agent['id']}",
            "agent_name": agent.get("agent_urn") or f"urn:agent:marketplace:{label.replace(' ', '')}",
            "label": label,
            "description": agent.get("description") or "",
            "version": agent.get("version", "1.0.0"),
            "jurisdiction": agent.get("jurisdiction"),
            "provider": {
                "name": provider_org.get("name", ""),
                "url": agent.get("access_point_url", ""),
            },
            "endpoints": endpoints,
            "capabilities": caps,
            "skills": skills,
            "inputSchema": input_schema,
            "outputSchema": output_schema,
            "modelProvider": agent.get("model_provider"),
            "sla": sla,
            "pricing": pricing,
        },
    }


@router.get("/catalog")
async def get_catalog():
    """Return the current catalog of active agents (used by smoke test and frontend)."""
    agents = await repo.list_agents()
    active_agents = [a for a in agents if a["status"] == "active"]
    resources = [_agent_to_beckn_resource(a) for a in active_agents]
    return {"resources": resources, "total": len(resources)}


@router.post("/publish")
async def publish_catalog():
    """Publish all active agents from DB to the Beckn CDS."""
    agents = await repo.list_agents()
    active_agents = [a for a in agents if a["status"] == "active"]

    if not active_agents:
        return {"status": "empty", "message": "No active agents to publish"}

    resources = [_agent_to_beckn_resource(a) for a in active_agents]

    provider_org = active_agents[0].get("provider_org", {})
    if isinstance(provider_org, str):
        provider_org = json.loads(provider_org)

    catalog = {
        "id": "catalog-ai-agents-db",
        "descriptor": {
            "name": "AI Agent Catalog",
            "shortDesc": f"Catalog with {len(resources)} AI agents from database",
        },
        "provider": {
            "id": str(active_agents[0]["provider_id"]),
            "descriptor": {"name": provider_org.get("name", "Provider")},
        },
        "resources": resources,
        "offers": [
            {
                "id": f"offer-agent-{a['id']}",
                "descriptor": {"name": json.loads(a['agent_name'])['en'] if isinstance(a['agent_name'], str) else a['agent_name'].get('en', 'Agent')},
                "resourceIds": [str(a["id"])],
                "provider": {"id": str(a["provider_id"])},
            }
            for a in active_agents
        ],
        "publishDirectives": {"catalogType": "regular"},
    }

    dt = datetime.now(timezone.utc)
    timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    payload = {
        "context": {
            "networkId": NETWORK_ID,
            "action": "catalog/publish",
            "version": "2.0.0",
            "bapId": "bap.example.com",
            "bapUri": "http://onix-bap:8081/bap/receiver",
            "bppId": BPP_ID,
            "bppUri": BPP_URI,
            "transactionId": str(uuid.uuid4()),
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
            result = response.json()
            logger.info(f"publish sent to CDS — HTTP {response.status_code}, {len(resources)} agents")
            return {
                "status": "sent",
                "fabric": {
                    "catalogPublished": response.status_code == 200,
                    "agentsInCatalog": len(resources),
                },
                "transactionId": payload["context"]["transactionId"],
            }
    except Exception as e:
        logger.error(f"publish failed: {e}")
        return {"status": "error", "detail": str(e)}


# ─── Transactions ────────────────────────────────────────────

@router.get("/transactions")
async def list_transactions():
    return await repo.list_contracts()


# ─── Health ──────────────────────────────────────────────────

@router.get("/health")
async def health():
    from app.config import SERVICE_NAME
    from app.db.pool import get_pool
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return {"status": "ok", "service": SERVICE_NAME, "database": db_status}
