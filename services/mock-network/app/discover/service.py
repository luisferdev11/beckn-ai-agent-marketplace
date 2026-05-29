"""Discover orchestration.

Owns:

  process_discover()    Parse envelope, run retrieval, assemble catalogs.
  dispatch_on_discover() POST the assembled envelope back to the BAP.

Catalog grouping rule: one ``catalog`` per BPP. Even if Tecla and Serg
both match, the BAP gets two entries in ``message.catalogs`` so the
provider attribution stays clean. This matches what the smoke test
already inspects and is the canonical Beckn v2 shape.

Callback delivery: same pattern as on_publish — we bypass ONIX and POST
directly to the BAP backend via the Registry's ``backend_health_url``.
Documented as the MVP simplification in ``app.catalog.service``.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.discover import query as discover_query
from app.discover.models import DiscoverQuery, from_envelope
from app.embeddings.service import EmbeddingService
from app.registry import repository as registry_repository

logger = logging.getLogger(__name__)


CALLBACK_TIMEOUT_SECONDS = 10.0


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ── Catalog assembly ──────────────────────────────────────────────


def _row_to_resource(row: dict) -> dict:
    """Map an ``agent_versions`` row into a Beckn ``Resource`` block.

    ``resourceAttributes`` is the AgentFacts JSON we stored verbatim at
    publish time, so this is round-trippable: the BAP sees exactly what
    the BPP declared. We append two marketplace-internal keys to
    ``resourceAttributes`` — prefixed with an underscore so partners can
    distinguish them from declared AgentFacts fields:

      ``_marketplaceScore``  the composite 0..1 score used for ranking
      ``_marketplaceScoreComponents``  the three components (semantic,
                                       freshness, health) so the BAP /
                                       portal can explain why a result
                                       ranked where it did.

    Both keys are optional — a row missing ``score`` (e.g. assembled
    outside the discover pipeline) skips them.
    """
    resource = {
        "id": row["beckn_id"],
        "descriptor": {
            "name": row.get("label") or "AI Agent",
            "shortDesc": (row.get("description") or "")[:200],
            "longDesc": row.get("description") or "",
        },
        "resourceAttributes": dict(row.get("agent_facts") or {}),
    }
    if "score" in row:
        resource["resourceAttributes"]["_marketplaceScore"] = float(row["score"])
        resource["resourceAttributes"]["_marketplaceScoreComponents"] = {
            "semantic": float(row.get("similarity") or 0.0),
            "freshness": float(row.get("freshness") or 0.0),
            "health": float(row.get("health_value") or 0.0),
            "quality": float(row.get("quality_value") or 0.0),
            "ratingCount": int(row.get("rating_count") or 0),
        }
    return resource


async def assemble_catalogs(
    candidates: list[dict],
    transaction_id: str,
) -> list[dict]:
    """Group candidates by bpp_subscriber_id and decorate with provider info.

    Provider descriptor is read from the Registry (``subscribers.organization``)
    — that is the source of truth for who a BPP is. If a provider has
    been deprecated since publish we still surface their existing
    indexed agents (no join-time filter); a periodic catalog cleanup
    job is a separate concern (Pieza 4).

    Catalog ordering follows the highest composite ``score`` present in
    each BPP's row group — so a provider whose best agent ranks higher
    appears earlier in ``message.catalogs``. Within a catalog, resources
    keep the candidate order (already sorted by composite score upstream).
    """
    # Preserve candidate order within each BPP group so the rank is
    # observable end-to-end. OrderedDict keeps insertion order.
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for row in candidates:
        bpp_id = row.get("bpp_subscriber_id") or "unknown"
        groups.setdefault(bpp_id, []).append(row)

    def _max_score(rows: list[dict]) -> float:
        return max((float(r.get("score") or 0.0) for r in rows), default=0.0)

    ordered_bpp_ids = sorted(groups.keys(), key=lambda b: _max_score(groups[b]), reverse=True)

    catalogs: list[dict] = []
    for bpp_id in ordered_bpp_ids:
        rows = groups[bpp_id]
        subscriber = await registry_repository.get_subscriber(bpp_id)
        if subscriber is None:
            provider_desc = {"name": bpp_id}
            bpp_uri = None
        else:
            org = subscriber.get("organization") or {}
            provider_desc = {
                "name": org.get("name") or bpp_id,
                "shortDesc": org.get("shortDesc") or "",
            }
            bpp_uri = subscriber.get("endpoint_url")

        provider_block: dict = {
            "id": bpp_id,
            "descriptor": provider_desc,
        }
        # Expose the BPP's ONIX endpoint so BAPs can route subsequent
        # actions (select / init / confirm / status / rate) back to the
        # right BPP after a multi-provider discover. Without this the
        # BAP would default to its statically-configured BPP_URI and
        # mis-route any pick that is not the default provider.
        # The field rides on the JSON-LD-flexible Organization block
        # (Beckn v2 does not formalise `endpoints` here yet) and is
        # documented as a network-local extension.
        if bpp_uri:
            provider_block["endpoints"] = {"beckn": bpp_uri}

        catalogs.append({
            "id": f"catalog-discover-{transaction_id[:8]}-{bpp_id}",
            "descriptor": {
                "name": f"{provider_desc['name']} — AI Agents",
                "shortDesc": f"{len(rows)} matching agents",
            },
            "provider": provider_block,
            "resources": [_row_to_resource(r) for r in rows],
        })
    return catalogs


# ── Top-level orchestration ───────────────────────────────────────


async def process_discover(
    envelope: dict,
    *,
    embedder: Optional[EmbeddingService] = None,
) -> dict:
    """End-to-end: envelope in, on_discover envelope out.

    Returned envelope is built but NOT yet dispatched. The caller
    (route layer) hands it to ``dispatch_on_discover`` in a background
    task so the inbound ACK stays sync-fast.
    """
    parsed: DiscoverQuery = from_envelope(envelope)
    transaction_id = (envelope.get("context") or {}).get("transactionId") or ""

    candidates = await discover_query.retrieve_candidates(parsed, embedder=embedder)
    catalogs = await assemble_catalogs(candidates, transaction_id)

    logger.info(
        "discover: txn=%s candidates=%d catalogs=%d text_search=%r",
        transaction_id[:8] if transaction_id else "?",
        len(candidates), len(catalogs),
        parsed.text_search[:60],
    )

    incoming_context = envelope.get("context") or {}
    out_context = {**incoming_context}
    out_context["action"] = "on_discover"
    out_context["timestamp"] = _now_iso()

    return {
        "context": out_context,
        "message": {"catalogs": catalogs},
    }


# ── on_discover callback dispatch ─────────────────────────────────


async def dispatch_on_discover(envelope: dict) -> None:
    """POST the on_discover envelope to the BAP backend.

    Resolves the destination via the Registry: ``bap_subscriber_id`` from
    ``context.bapId`` → ``subscriber.backend_health_url`` → BAP webhook.

    Failures are logged and swallowed; one bad BAP cannot stall the CDS
    background loop. The BAP can always re-issue a discover.
    """
    context = envelope.get("context") or {}
    bap_subscriber_id = context.get("bapId") or ""
    if not bap_subscriber_id:
        logger.warning("on_discover: missing bapId — cannot deliver callback")
        return

    subscriber = await registry_repository.get_subscriber(bap_subscriber_id)
    if subscriber is None:
        logger.warning(
            "on_discover: unknown bapId=%s — cannot deliver callback",
            bap_subscriber_id,
        )
        return

    backend_url = subscriber.get("backend_health_url")
    if not backend_url:
        logger.warning(
            "on_discover: subscriber %s has no backend_health_url — skipping",
            bap_subscriber_id,
        )
        return

    target = backend_url.rstrip("/") + "/api/bap-webhook/on_discover"
    try:
        async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SECONDS) as client:
            resp = await client.post(target, json=envelope)
        logger.info(
            "on_discover: delivered to %s → HTTP %d", target, resp.status_code
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("on_discover: delivery to %s failed: %s", target, exc)
