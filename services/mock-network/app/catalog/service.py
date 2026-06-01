"""Catalog publish orchestration.

The route layer calls ``process_publish`` after acknowledging the request.
This module knows the publish-pipeline rules — every Beckn-related state
transition lives here, not in routes or repository.

Pipeline per resource:

  1. Validate ``resource.resourceAttributes`` against AgentFacts.
  2. If invalid: record an ItemError, skip to next resource.
  3. Embed the agent's prose (text_for_agent + EmbeddingService.embed).
  4. Upsert into ``agent_versions`` (auto-deprecating older versions).

Pipeline per request:

  1. Pre-flight: bppId must match a known active subscriber.
  2. Insert PENDING row into ``published_catalogs``.
  3. Run per-resource pipeline.
  4. Update the publish row with aggregate status + per-item errors.
  5. POST on_publish to the BPP backend (best-effort).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app import config
from app.catalog import repository
from app.catalog.validation import (
    AgentFactsValidator,
    ItemError,
    get_default_validator,
    missing_schema_contracts,
)
from app.embeddings.service import EmbeddingService, embed_agent, get_default_service
from app.registry import repository as registry_repository

logger = logging.getLogger(__name__)


CALLBACK_TIMEOUT_SECONDS = 10.0


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ── DTOs we build progressively per request ────────────────────────


class CatalogProcessingError(Exception):
    """Raised when the publish request is too malformed to even index.

    The route handler turns this into HTTP 400 BEFORE the background task
    starts; once we are async, every individual item-level problem is a
    soft error reported in on_publish.results.
    """


# ── Top-level orchestration ────────────────────────────────────────


async def process_publish(
    envelope: dict,
    *,
    validator: Optional[AgentFactsValidator] = None,
    embedder: Optional[EmbeddingService] = None,
) -> list[dict]:
    """Run the full publish pipeline. Returns one result block per catalog
    in the request (the shape on_publish.message.results expects).

    Any unexpected exception aborts the request — we never want to
    leave the audit log in PENDING. The route layer catches and POSTs
    a REJECTED on_publish anyway.
    """
    validator = validator or get_default_validator()
    embedder = embedder or get_default_service()

    context = envelope.get("context") or {}
    transaction_id = context.get("transactionId") or ""
    message_id = context.get("messageId") or ""
    bpp_subscriber_id = context.get("bppId") or ""

    catalogs = (envelope.get("message") or {}).get("catalogs") or []
    if not catalogs:
        raise CatalogProcessingError("message.catalogs is empty or missing")

    results: list[dict] = []
    for catalog in catalogs:
        result = await _process_one_catalog(
            catalog=catalog,
            envelope=envelope,
            transaction_id=transaction_id,
            message_id=message_id,
            bpp_subscriber_id=bpp_subscriber_id,
            validator=validator,
            embedder=embedder,
        )
        results.append(result)

    return results


async def _process_one_catalog(
    *,
    catalog: dict,
    envelope: dict,
    transaction_id: str,
    message_id: str,
    bpp_subscriber_id: str,
    validator: AgentFactsValidator,
    embedder: EmbeddingService,
) -> dict:
    catalog_id = catalog.get("id")
    resources = catalog.get("resources") or []

    publish_id = await repository.record_publish(
        transaction_id=transaction_id,
        message_id=message_id,
        bpp_subscriber_id=bpp_subscriber_id,
        catalog_id=catalog_id,
        raw_payload=envelope,
    )

    accepted: list[str] = []
    rejected: list[ItemError] = []

    strict = config.strict_schemas()

    for res in resources:
        resource_id = res.get("id") or ""
        agent_facts = res.get("resourceAttributes") or {}

        errors = validator.validate_one(resource_id, agent_facts)
        if errors:
            rejected.extend(errors)
            logger.info(
                "catalog/publish: rejecting %s (%d errors)",
                resource_id, len(errors),
            )
            continue

        # Schema-contract gate (Epic D). In strict mode an agent missing
        # either rigorous input/output schema is rejected; in permissive
        # mode it is indexed but flagged ``pipeline_eligible=false`` so the
        # probe/orchestrator know not to route real work to it.
        missing = missing_schema_contracts(agent_facts)
        if missing and strict:
            rejected.append(ItemError(
                resource_id=resource_id,
                code="MISSING_SCHEMA_CONTRACT",
                message=("missing required schema contract(s): "
                         f"{', '.join(missing)} — declare a non-empty JSON Schema "
                         "for each (strict mode; set STRICT_SCHEMAS=false to relax)"),
                path="$." + missing[0],
            ))
            logger.info(
                "catalog/publish: rejecting %s — missing schema contracts %s",
                resource_id, missing,
            )
            continue

        # Inject pipeline_eligible AFTER AgentFacts validation: the schema
        # has additionalProperties:false, so an extra key would fail the
        # validator. discover returns agent_facts verbatim, surfacing the
        # flag to the frontend.
        indexed_facts = {**agent_facts, "pipeline_eligible": not missing}

        try:
            await _index_one_resource(
                agent_facts=indexed_facts,
                resource_id=resource_id,
                bpp_subscriber_id=bpp_subscriber_id,
                embedder=embedder,
            )
            accepted.append(resource_id)
        except Exception as exc:  # noqa: BLE001 — per-item isolation
            logger.warning(
                "catalog/publish: index failed for %s: %s", resource_id, exc
            )
            rejected.append(ItemError(
                resource_id=resource_id,
                code="INDEX_FAILED",
                message=str(exc),
                path="$",
            ))

    if rejected and accepted:
        status = "PARTIAL"
    elif rejected:
        status = "REJECTED"
    else:
        status = "ACCEPTED"

    errors_payload = [
        {
            "resourceId": e.resource_id,
            "code": e.code,
            "message": e.message,
            "path": e.path,
        }
        for e in rejected
    ]

    await repository.update_publish_result(
        publish_id,
        status=status,
        item_count=len(resources),
        item_count_accepted=len(accepted),
        item_count_rejected=len(rejected),
        errors=errors_payload,
    )

    logger.info(
        "catalog/publish: catalog=%s status=%s accepted=%d rejected=%d",
        catalog_id, status, len(accepted), len(rejected),
    )

    return {
        "catalogId": catalog_id,
        "status": status,
        "stats": {
            "itemCount": len(resources),
            "itemCountAccepted": len(accepted),
            "itemCountRejected": len(rejected),
        },
        "errors": errors_payload,
    }


async def _index_one_resource(
    *,
    agent_facts: dict,
    resource_id: str,
    bpp_subscriber_id: str,
    embedder: EmbeddingService,
) -> None:
    """Upsert one validated resource into agent_versions."""
    agent_urn = agent_facts["agent_name"]
    version = agent_facts["version"]
    label = agent_facts["label"]

    capabilities = agent_facts.get("capabilities") or {}
    skills_raw = agent_facts.get("skills") or []
    capability_tags: list[str] = []
    languages: set[str] = set()
    input_modes: set[str] = set()
    output_modes: set[str] = set()
    for skill in skills_raw if isinstance(skills_raw, list) else []:
        if not isinstance(skill, dict):
            continue
        sid = skill.get("id")
        if isinstance(sid, str) and sid:
            capability_tags.append(sid)
        for code in skill.get("supportedLanguages") or []:
            if isinstance(code, str):
                languages.add(code)
        for mode in skill.get("inputModes") or []:
            if isinstance(mode, str):
                input_modes.add(mode)
        for mode in skill.get("outputModes") or []:
            if isinstance(mode, str):
                output_modes.add(mode)
    if not capability_tags and isinstance(capabilities, dict):
        # Fallback: some catalogs only declare modalities at the
        # capabilities level. We still index that so a discover
        # filtered by modality finds something.
        for mod in capabilities.get("modalities") or []:
            if isinstance(mod, str):
                capability_tags.append(mod)

    pricing = agent_facts.get("pricing") or {}
    pricing_currency = pricing.get("currency") if isinstance(pricing, dict) else None
    pricing_value = pricing.get("value") if isinstance(pricing, dict) else None
    if isinstance(pricing_value, str):
        try:
            pricing_value = float(pricing_value)
        except (TypeError, ValueError):
            pricing_value = None

    sla = agent_facts.get("sla") or {}
    sla_max_latency_ms = sla.get("maxLatencyMs") if isinstance(sla, dict) else None

    embedding = embed_agent(agent_facts, service=embedder)

    await repository.upsert_agent_version(
        agent_urn=agent_urn,
        version=version,
        bpp_subscriber_id=bpp_subscriber_id,
        beckn_id=resource_id,
        agentfacts_id=agent_facts.get("id"),
        label=label,
        description=agent_facts.get("description") or "",
        jurisdiction=agent_facts.get("jurisdiction"),
        languages=sorted(languages),
        capability_tags=capability_tags,
        input_modes=sorted(input_modes),
        output_modes=sorted(output_modes),
        pricing_currency=pricing_currency,
        pricing_value=pricing_value,
        sla_max_latency_ms=sla_max_latency_ms,
        agent_facts=agent_facts,
        embedding=embedding,
    )


# ── on_publish callback dispatch ───────────────────────────────────


def _build_on_publish_envelope(
    incoming_context: dict,
    results: list[dict],
) -> dict:
    """Construct the Beckn on_publish envelope from the incoming context."""
    out_context = {**incoming_context}
    out_context["action"] = "catalog/on_publish"
    out_context["timestamp"] = _now_iso()
    return {
        "context": out_context,
        "message": {"results": results},
    }


async def dispatch_on_publish(
    envelope: dict,
    results: list[dict],
) -> None:
    """POST on_publish back to the BPP backend.

    MVP simplification: we bypass ONIX on the callback path and POST
    directly to the BPP backend's webhook (resolved via the Registry's
    backend_health_url). Real Beckn would route through ONIX-BPP
    receiver, which requires the CDS to own a signing key.
    """
    incoming_context = envelope.get("context") or {}
    bpp_subscriber_id = incoming_context.get("bppId") or ""

    callback_envelope = _build_on_publish_envelope(incoming_context, results)

    subscriber = await registry_repository.get_subscriber(bpp_subscriber_id)
    if subscriber is None:
        logger.warning(
            "on_publish: unknown bppId=%s — cannot deliver callback", bpp_subscriber_id
        )
        return

    backend_url = subscriber.get("backend_health_url")
    if not backend_url:
        logger.warning(
            "on_publish: subscriber %s has no backend_health_url — skipping",
            bpp_subscriber_id,
        )
        return

    target = backend_url.rstrip("/") + "/api/webhook/on_publish"
    try:
        async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SECONDS) as client:
            resp = await client.post(target, json=callback_envelope)
        logger.info(
            "on_publish: delivered to %s → HTTP %d", target, resp.status_code
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("on_publish: delivery to %s failed: %s", target, exc)
