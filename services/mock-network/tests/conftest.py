"""Mock-network test fixtures.

The Registry and Catalog repositories normally talk to ``postgres-mocknet``
via asyncpg. For unit and integration tests we replace each repository
function with an in-memory implementation so the suite is fast and runnable
offline. Real DB behaviour is exercised by explicit smokes against the live
container.

Fixtures provided:

  app                  FastAPI app from ``app.main``. Lifespan is intentionally
                       NOT triggered by AsyncClient/ASGITransport defaults so
                       the real pool never opens.

  client               httpx AsyncClient bound to the app.

  fake_subscribers     Autouse. Seeds the registry in-memory store and patches
                       ``app.registry.repository``.

  fake_catalog_store   Autouse. Patches ``app.catalog.repository`` with an
                       in-memory implementation. Yields a dict so tests can
                       introspect what was published.

  fake_embedder        Autouse. Replaces the default EmbeddingService with a
                       deterministic fake (hashed-text → 384-dim vector) so
                       no model is loaded during tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _seed_rows() -> dict[str, dict]:
    """Same three identities the SQL migration seeds. Kept in sync by hand."""
    return {
        "bap.example.com": {
            "id": 1,
            "subscriber_id": "bap.example.com",
            "role": "BAP",
            "endpoint_url": "http://onix-bap:8081/bap/receiver",
            "backend_health_url": "http://bap-marketplace:3001",
            "public_key": "g/3swjI93IhZ0SScrVZapeLjU+W0AeiSid3LViYZJFo=",
            "organization": {"name": "Demo Buyer Marketplace", "shortDesc": "Reference BAP"},
            "jurisdiction": "IND",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        "bpp.example.com": {
            "id": 2,
            "subscriber_id": "bpp.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp:8082/bpp/receiver",
            "backend_health_url": "http://bpp-provider:3002",
            "public_key": "CqVy97DW45bcZPPrWIYGe2ldl9C93NFeVciiAEYsvR0=",
            "organization": {"name": "General Tecla Industries", "shortDesc": "Demo provider"},
            "jurisdiction": "IND",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        "bpp-serg.example.com": {
            "id": 3,
            "subscriber_id": "bpp-serg.example.com",
            "role": "BPP",
            "endpoint_url": "http://onix-bpp-serg:8083/bpp/receiver",
            "backend_health_url": "http://bpp-serg:3005",
            "public_key": "bfbdo3TxLzSRutUMSjl+OeDtZgqVDlCuLbR2aDbtPN0=",
            "organization": {"name": "Serg Ops", "shortDesc": "Second demo provider"},
            "jurisdiction": "MEX",
            "status": "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    }


@pytest.fixture
def app():
    from app.main import app
    return app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def fake_subscribers(monkeypatch):
    """In-memory replacement for ``app.registry.repository``."""
    store: dict[str, dict] = _seed_rows()
    next_id = [max(row["id"] for row in store.values()) + 1] if store else [1]

    async def _create(data: dict) -> dict:
        sid = data["subscriber_id"]
        if sid in store:
            raise ValueError(f"subscriber {sid} already exists")
        row = {
            "id": next_id[0],
            "subscriber_id": sid,
            "role": data["role"],
            "endpoint_url": data["endpoint_url"],
            "backend_health_url": data.get("backend_health_url"),
            "public_key": data.get("public_key"),
            "organization": data.get("organization") or {},
            "jurisdiction": data.get("jurisdiction"),
            "status": data.get("status") or "active",
            "health": "unknown",
            "last_seen_at": None,
            "consecutive_failures": 0,
            "kyc_data": {},
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        store[sid] = row
        next_id[0] += 1
        return dict(row)

    async def _get(subscriber_id: str) -> Optional[dict]:
        row = store.get(subscriber_id)
        return dict(row) if row else None

    async def _list(role: Optional[str] = None, status_filter: Optional[str] = None) -> list[dict]:
        rows = list(store.values())
        if role:
            rows = [r for r in rows if r["role"] == role]
        if status_filter:
            rows = [r for r in rows if r["status"] == status_filter]
        return [dict(r) for r in rows]

    async def _update(subscriber_id: str, **fields) -> Optional[dict]:
        row = store.get(subscriber_id)
        if not row:
            return None
        for k, v in fields.items():
            if v is not None:
                row[k] = v
        row["updated_at"] = _now_iso()
        return dict(row)

    async def _deactivate(subscriber_id: str) -> Optional[dict]:
        return await _update(subscriber_id, status="deprecated")

    async def _update_health(
        subscriber_id: str,
        *,
        health: str,
        last_seen_at: Optional[str],
        consecutive_failures: int,
    ) -> None:
        row = store.get(subscriber_id)
        if not row:
            return
        row["health"] = health
        row["last_seen_at"] = last_seen_at
        row["consecutive_failures"] = consecutive_failures
        row["updated_at"] = _now_iso()

    from app.registry import repository
    monkeypatch.setattr(repository, "create_subscriber", _create)
    monkeypatch.setattr(repository, "get_subscriber", _get)
    monkeypatch.setattr(repository, "list_subscribers", _list)
    monkeypatch.setattr(repository, "update_subscriber", _update)
    monkeypatch.setattr(repository, "deactivate_subscriber", _deactivate)
    monkeypatch.setattr(repository, "update_health", _update_health)

    yield store

    store.clear()


# ─── Catalog (Pieza 1) fakes ────────────────────────────────────────


@pytest.fixture(autouse=True)
def fake_catalog_store(monkeypatch):
    """In-memory replacement for ``app.catalog.repository``."""
    publishes: dict[int, dict] = {}
    agents: list[dict] = []
    next_pub_id = [1]
    next_agent_id = [1]

    async def _record_publish(*, transaction_id, message_id, bpp_subscriber_id,
                              catalog_id, raw_payload):
        pid = next_pub_id[0]
        next_pub_id[0] += 1
        publishes[pid] = {
            "id": pid,
            "transaction_id": transaction_id,
            "message_id": message_id,
            "bpp_subscriber_id": bpp_subscriber_id,
            "catalog_id": catalog_id,
            "raw_payload": raw_payload,
            "status": "PENDING",
            "item_count": 0,
            "item_count_accepted": 0,
            "item_count_rejected": 0,
            "errors": [],
        }
        return pid

    async def _update_publish_result(publish_id, *, status, item_count,
                                     item_count_accepted, item_count_rejected,
                                     errors):
        row = publishes.get(publish_id)
        if not row:
            return
        row.update({
            "status": status,
            "item_count": item_count,
            "item_count_accepted": item_count_accepted,
            "item_count_rejected": item_count_rejected,
            "errors": errors,
        })

    async def _upsert_agent_version(**kwargs):
        urn = kwargs["agent_urn"]
        ver = kwargs["version"]
        for row in agents:
            if (row["agent_urn"] == urn
                    and row["version"] != ver
                    and row["status"] == "current"):
                row["status"] = "deprecated"
        existing = next(
            (r for r in agents if r["agent_urn"] == urn and r["version"] == ver),
            None,
        )
        if existing:
            existing.update({**kwargs, "status": "current"})
            return existing["id"]
        new_id = next_agent_id[0]
        next_agent_id[0] += 1
        agents.append({"id": new_id, "status": "current", **kwargs})
        return new_id

    async def _count_current_agents(bpp_subscriber_id=None):
        if bpp_subscriber_id is None:
            return sum(1 for a in agents if a["status"] == "current")
        return sum(
            1 for a in agents
            if a["status"] == "current" and a["bpp_subscriber_id"] == bpp_subscriber_id
        )

    from app.catalog import repository as catalog_repo
    monkeypatch.setattr(catalog_repo, "record_publish", _record_publish)
    monkeypatch.setattr(catalog_repo, "update_publish_result", _update_publish_result)
    monkeypatch.setattr(catalog_repo, "upsert_agent_version", _upsert_agent_version)
    monkeypatch.setattr(catalog_repo, "count_current_agents", _count_current_agents)

    yield {"publishes": publishes, "agents": agents}

    publishes.clear()
    agents.clear()


# ─── Embedding fake ─────────────────────────────────────────────────


class _FakeEmbeddingService:
    """Deterministic stand-in for sentence-transformers.

    Maps every distinct input text to a stable 384-dim vector derived
    from SHA-256 bits, so two embeddings of the same string compare
    equal and embeddings of different strings differ.
    """

    EMBEDDING_DIM = 384

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.EMBEDDING_DIM
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        seed = (h * ((self.EMBEDDING_DIM // len(h)) + 1))[: self.EMBEDDING_DIM]
        return [(b / 255.0) * 2.0 - 1.0 for b in seed]


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    """Replace the module-level singleton with the fake service."""
    from app.embeddings import service as emb_service
    fake = _FakeEmbeddingService()
    monkeypatch.setattr(emb_service, "_default_service", fake)
    yield fake


# ─── Discover (Pieza 2) fakes ───────────────────────────────────────


@pytest.fixture(autouse=True)
def fake_ratings_repo(monkeypatch):
    """In-memory replacement for ``app.ratings.repository``.

    Keyed by (bpp_subscriber_id, agent_beckn_id); each call adds one
    sample to the rolling count/sum/avg, matching the SQL semantics
    in ``ingest_rating``. Yields the underlying dict so tests can
    introspect / pre-seed.
    """
    from datetime import datetime, timezone

    store: dict[tuple[str, str], dict] = {}

    async def _ingest(*, bpp_subscriber_id, agent_beckn_id, score, rated_at=None):
        key = (bpp_subscriber_id, agent_beckn_id)
        ts = rated_at or datetime.now(timezone.utc)
        row = store.get(key)
        if row is None:
            row = {
                "bpp_subscriber_id": bpp_subscriber_id,
                "agent_beckn_id":    agent_beckn_id,
                "rating_count":      1,
                "rating_sum":        float(score),
                "avg_score":         float(score),
                "last_rated_at":     ts,
                "last_updated_at":   ts,
            }
        else:
            row["rating_count"] += 1
            row["rating_sum"]   += float(score)
            row["avg_score"]     = row["rating_sum"] / row["rating_count"]
            row["last_rated_at"] = ts
            row["last_updated_at"] = ts
        store[key] = dict(row)
        return dict(row)

    async def _get(*, bpp_subscriber_id, agent_beckn_id):
        row = store.get((bpp_subscriber_id, agent_beckn_id))
        return dict(row) if row else None

    from app.ratings import repository as ratings_repo
    monkeypatch.setattr(ratings_repo, "ingest_rating", _ingest)
    monkeypatch.setattr(ratings_repo, "get_aggregate", _get)

    yield store
    store.clear()


@pytest.fixture
def fake_discover_index(monkeypatch):
    """In-memory candidate store for ``app.discover.query.retrieve_candidates``.

    Not autouse — discover tests opt in by requesting the fixture and
    seeding ``store.rows`` with the candidate dicts they want returned.
    The fake honours the structured filters and respects the ``limit``
    so tests can verify the route honours them too.

    Composite ranking: rows may carry ``published_at`` and ``bpp_health``
    so tests can exercise the composite-score ordering. When omitted, the
    fake supplies neutral defaults (now-published, ``unknown`` health) so
    legacy tests that only care about filters keep working.
    """
    from app.discover import scoring

    class _Store:
        def __init__(self):
            self.rows: list[dict] = []
            self.last_query = None

    store = _Store()

    async def _retrieve(query, *, embedder=None):
        store.last_query = query
        f = query.filters
        filtered: list[dict] = []
        for row in store.rows:
            if f.jurisdiction and row.get("jurisdiction") != f.jurisdiction:
                continue
            if f.languages and not set(f.languages).issubset(set(row.get("languages") or [])):
                continue
            if f.capabilities and not set(f.capabilities).issubset(set(row.get("capability_tags") or [])):
                continue
            if f.currency and row.get("pricing_currency") != f.currency:
                continue
            pv = row.get("pricing_value")
            if f.max_price_value is not None and pv is not None and pv > f.max_price_value:
                continue
            ml = row.get("sla_max_latency_ms")
            if f.max_latency_ms is not None and ml is not None and ml > f.max_latency_ms:
                continue
            similarity = float(row.get("similarity") or 0.0)
            freshness = scoring.freshness_score(published_at=row.get("published_at"))
            health = scoring.health_score(row.get("bpp_health"))
            quality = scoring.quality_score(
                avg_rating=row.get("avg_rating"),
                rating_count=int(row.get("rating_count") or 0),
            )
            score = scoring.composite_score(
                semantic=similarity, freshness=freshness,
                health=health, quality=quality,
            )
            filtered.append({
                **row,
                "similarity": similarity,
                "bpp_health": row.get("bpp_health") or "unknown",
                "freshness": freshness,
                "health_value": health,
                "quality_value": quality,
                "rating_count": int(row.get("rating_count") or 0),
                "score": score,
            })
        filtered.sort(
            key=lambda r: (r["score"], r.get("similarity", 0.0)),
            reverse=True,
        )
        return filtered[: query.limit]

    from app.discover import query as discover_query
    monkeypatch.setattr(discover_query, "retrieve_candidates", _retrieve)
    yield store
