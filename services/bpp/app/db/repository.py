"""BPP database repository — all PostgreSQL queries for the provider side."""
from __future__ import annotations

import json
import logging
from beckn_models.db import get_pool

logger = logging.getLogger(__name__)


# ─── Categories ──────────────────────────────────────────────

async def create_category(name: str, display_name: dict, description: str | None = None):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO categories (name, display_name, description)
           VALUES ($1, $2, $3)
           ON CONFLICT (name) DO UPDATE SET display_name = $2, description = $3
           RETURNING id, name, display_name, description, is_active""",
        name, json.dumps(display_name), description,
    )
    return dict(row)


async def list_categories():
    pool = await get_pool()
    rows = await pool.fetch("SELECT id, name, display_name, description, is_active FROM categories ORDER BY id")
    return [dict(r) for r in rows]


async def get_category_by_id(category_id: int):
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM categories WHERE id = $1", category_id)
    return dict(row) if row else None


async def get_category_by_name(name: str):
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM categories WHERE name = $1", name)
    return dict(row) if row else None


# ─── Providers ───────────────────────────────────────────────

async def create_provider(subscriber_id: str, bpp_uri: str, public_key: str | None,
                          organization: dict):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO providers (subscriber_id, bpp_uri, public_key, organization)
           VALUES ($1, $2, $3, $4)
           RETURNING id, subscriber_id, bpp_uri, public_key, organization, status, created_at""",
        subscriber_id, bpp_uri, public_key, json.dumps(organization),
    )
    return dict(row)


async def list_providers():
    pool = await get_pool()
    rows = await pool.fetch("SELECT id, subscriber_id, bpp_uri, organization, status, created_at FROM providers ORDER BY id")
    return [dict(r) for r in rows]


async def get_provider_by_id(provider_id: int):
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM providers WHERE id = $1", provider_id)
    return dict(row) if row else None


# ─── Agents ──────────────────────────────────────────────────

async def create_agent(provider_id: int, category_id: int, agent_name: dict,
                       access_point_url: str | None = None,
                       interaction_type: str = "sync",
                       version: str = "1.0.0",
                       capabilities: list | None = None,
                       skills: list | None = None,
                       input_schema: dict | None = None,
                       output_schema: dict | None = None,
                       pricing_model: dict | None = None,
                       sla: dict | None = None,
                       jurisdiction: str | None = None,
                       endpoints: dict | None = None,
                       modalities: list | None = None,
                       authentication: dict | None = None,
                       description: str | None = None):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO agents (provider_id, category_id, agent_name, description,
               access_point_url, interaction_type, version,
               capabilities, skills, input_schema, output_schema,
               pricing_model, sla, jurisdiction, endpoints, modalities, authentication)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
           RETURNING id, provider_id, category_id, agent_name, description, version,
                     access_point_url, interaction_type, capabilities, skills,
                     input_schema, output_schema, pricing_model, sla, jurisdiction,
                     endpoints, modalities, authentication, status, created_at""",
        provider_id, category_id, json.dumps(agent_name), description,
        access_point_url, interaction_type, version,
        json.dumps(capabilities or []),
        json.dumps(skills or []),
        json.dumps(input_schema or {}),
        json.dumps(output_schema or {}),
        json.dumps(pricing_model or {}),
        json.dumps(sla or {}),
        jurisdiction,
        json.dumps(endpoints or {"static": []}),
        json.dumps(modalities or ["text"]),
        json.dumps(authentication or {"methods": ["jwt"]}),
    )
    return dict(row)


async def update_agent(agent_id: int, **kwargs):
    pool = await get_pool()
    sets = []
    vals = []
    i = 1
    json_fields = {"agent_name", "capabilities", "skills", "input_schema", "output_schema",
                   "pricing_model", "sla", "endpoints", "modalities", "authentication"}
    for key, val in kwargs.items():
        sets.append(f"{key} = ${i}")
        vals.append(json.dumps(val) if key in json_fields else val)
        i += 1
    sets.append(f"updated_at = NOW()")
    vals.append(agent_id)
    query = f"UPDATE agents SET {', '.join(sets)} WHERE id = ${i} RETURNING *"
    row = await pool.fetchrow(query, *vals)
    return dict(row) if row else None


async def deactivate_agent(agent_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        "UPDATE agents SET status = 'inactive', updated_at = NOW() WHERE id = $1 RETURNING id, status",
        agent_id,
    )
    return dict(row) if row else None


async def list_agents():
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT a.*, c.name as category_name, p.organization as provider_org
           FROM agents a
           JOIN categories c ON a.category_id = c.id
           JOIN providers p ON a.provider_id = p.id
           ORDER BY a.id""",
    )
    return [dict(r) for r in rows]


async def get_agent_by_id(agent_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        """SELECT a.*, c.name as category_name, p.organization as provider_org, p.subscriber_id
           FROM agents a
           JOIN categories c ON a.category_id = c.id
           JOIN providers p ON a.provider_id = p.id
           WHERE a.id = $1""",
        agent_id,
    )
    return dict(row) if row else None


async def search_agents(keywords: list[str]):
    """Search agents by keywords matching capabilities, skills, agent_name, or description."""
    pool = await get_pool()
    conditions = []
    vals = []
    for i, kw in enumerate(keywords, 1):
        like_val = f"%{kw}%"
        param = f"${i}::text"
        conditions.append(
            f"(a.capabilities::text ILIKE {param} OR a.skills::text ILIKE {param} "
            f"OR a.agent_name::text ILIKE {param} OR COALESCE(a.description, '') ILIKE {param})"
        )
        vals.append(like_val)

    where = " OR ".join(conditions) if conditions else "TRUE"
    query = f"""SELECT a.*, c.name as category_name, p.organization as provider_org, p.subscriber_id
                FROM agents a
                JOIN categories c ON a.category_id = c.id
                JOIN providers p ON a.provider_id = p.id
                WHERE a.status = 'active' AND ({where})
                ORDER BY a.id"""
    rows = await pool.fetch(query, *vals)
    return [dict(r) for r in rows]


# ─── Contracts ───────────────────────────────────────────────

async def create_contract(contract_code: str, transaction_id: str, **kwargs):
    pool = await get_pool()
    json_fields = {"commitments", "consideration", "performance", "settlements", "participants"}
    row = await pool.fetchrow(
        """INSERT INTO contracts (contract_code, transaction_id, agent_id, provider_id,
               bap_id, bpp_id, status, commitments, consideration, performance,
               settlements, participants, total_amount, currency)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
           ON CONFLICT (transaction_id) DO UPDATE SET
               status = EXCLUDED.status,
               commitments = EXCLUDED.commitments,
               consideration = EXCLUDED.consideration
           RETURNING *""",
        contract_code,
        transaction_id,
        kwargs.get("agent_id"),
        kwargs.get("provider_id"),
        kwargs.get("bap_id"),
        kwargs.get("bpp_id"),
        kwargs.get("status", "DRAFT"),
        json.dumps(kwargs.get("commitments", [])),
        json.dumps(kwargs.get("consideration", [])),
        json.dumps(kwargs.get("performance", [])),
        json.dumps(kwargs.get("settlements", [])),
        json.dumps(kwargs.get("participants", [])),
        kwargs.get("total_amount"),
        kwargs.get("currency", "INR"),
    )
    return dict(row) if row else None


async def get_contract_by_txn(transaction_id: str):
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM contracts WHERE transaction_id = $1", transaction_id)
    return dict(row) if row else None


async def update_contract(transaction_id: str, **kwargs):
    pool = await get_pool()
    sets = []
    vals = []
    i = 1
    json_fields = {"commitments", "consideration", "performance", "settlements", "participants"}
    for key, val in kwargs.items():
        sets.append(f"{key} = ${i}")
        vals.append(json.dumps(val) if key in json_fields else val)
        i += 1
    vals.append(transaction_id)
    query = f"UPDATE contracts SET {', '.join(sets)} WHERE transaction_id = ${i} RETURNING *"
    row = await pool.fetchrow(query, *vals)
    return dict(row) if row else None


async def list_contracts():
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM contracts ORDER BY created_at DESC LIMIT 100")
    return [dict(r) for r in rows]
