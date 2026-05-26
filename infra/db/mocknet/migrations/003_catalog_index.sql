-- 003_catalog_index.sql — CDS catalog index tables.
--
-- Two tables drive the catalog publish/discover path:
--
-- 1. `agent_versions` — the searchable index. One row per (agent_urn, version)
--    snapshot of an AgentFacts document. Discover queries this table.
--    Includes a 384-dim embedding for semantic similarity (pgvector + HNSW)
--    and denormalised filter columns so JSONPath-style filtering on hot
--    paths can stay in pure SQL.
--
-- 2. `published_catalogs` — audit log of every `catalog/publish` POST the
--    CDS received from a BPP. Lets the on_publish callback report
--    per-catalog stats and lets operators see who published what when.
--
-- Both tables key off `subscribers.subscriber_id` (no real FK because the
-- subscriber may be removed before the catalog snapshot expires — the
-- soft-link semantics mirror how Beckn participants come and go).

-- ─── agent_versions ─────────────────────────────────────────────────

CREATE TABLE agent_versions (
    id                  SERIAL PRIMARY KEY,

    -- Identity
    agent_urn           TEXT NOT NULL,                                  -- urn:agent:bpp:Name (stable across versions)
    version             TEXT NOT NULL,                                  -- semver, e.g. "1.2.0"
    bpp_subscriber_id   TEXT NOT NULL,                                  -- soft-FK to subscribers.subscriber_id

    -- Beckn-side identifiers
    beckn_id            TEXT NOT NULL,                                  -- e.g. "agent-summarizer-001"; used as `resource.id`
    agentfacts_id       TEXT,                                           -- e.g. "marketplace:summarizer-v1"

    -- Display fields denormalised from agent_facts for SELECT speed
    label               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',

    -- Hard-filter columns denormalised from agent_facts. Discover applies
    -- these BEFORE the vector similarity scan so the candidate set is
    -- always tiny by the time we touch the embedding index.
    jurisdiction        TEXT,
    languages           TEXT[] NOT NULL DEFAULT '{}',
    capability_tags     TEXT[] NOT NULL DEFAULT '{}',                   -- e.g. {document_summary, legal_analysis}
    input_modes         TEXT[] NOT NULL DEFAULT '{}',
    output_modes        TEXT[] NOT NULL DEFAULT '{}',
    pricing_currency    CHAR(3),
    pricing_value       NUMERIC(12,4),
    sla_max_latency_ms  INTEGER,

    -- Source-of-truth: the full AgentFacts JSON document as received.
    -- on_discover returns this verbatim inside catalog.resources[].resourceAttributes.
    agent_facts         JSONB NOT NULL,

    -- Semantic search
    embedding           vector(384),

    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'current'
                        CHECK (status IN ('current', 'deprecated', 'sunset')),
    published_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_at       TIMESTAMPTZ,

    UNIQUE (agent_urn, version)
);

-- One "current" per agent_urn. When a new version is promoted, the
-- existing current row must be flipped to "deprecated" inside the same
-- transaction; this partial index guarantees we cannot leave two
-- current rows for the same URN.
CREATE UNIQUE INDEX idx_agent_versions_one_current
    ON agent_versions (agent_urn) WHERE status = 'current';

CREATE INDEX idx_agent_versions_status     ON agent_versions(status);
CREATE INDEX idx_agent_versions_bpp        ON agent_versions(bpp_subscriber_id);
CREATE INDEX idx_agent_versions_caps       ON agent_versions USING GIN(capability_tags);
CREATE INDEX idx_agent_versions_languages  ON agent_versions USING GIN(languages);

-- HNSW for sub-100ms cosine similarity at >100K rows. Built unfilled and
-- populated as catalogs publish.
CREATE INDEX idx_agent_versions_embedding_hnsw
    ON agent_versions USING hnsw (embedding vector_cosine_ops);


-- ─── published_catalogs ─────────────────────────────────────────────
--
-- One row per `catalog/publish` request the CDS receives. Drives both
-- the on_publish callback (which reports per-catalog stats) and the
-- operator's "publish history" view.

CREATE TABLE published_catalogs (
    id                      SERIAL PRIMARY KEY,
    transaction_id          TEXT NOT NULL,
    message_id              TEXT NOT NULL,
    bpp_subscriber_id       TEXT NOT NULL,                              -- soft-FK to subscribers
    catalog_id              TEXT,                                       -- catalog.id from the payload, if present

    raw_payload             JSONB NOT NULL,                             -- full request body, for replay/debug

    status                  TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'PARTIAL')),

    -- Per-catalog stats reported back in on_publish.message.results[]
    item_count              INTEGER NOT NULL DEFAULT 0,
    item_count_accepted     INTEGER NOT NULL DEFAULT 0,
    item_count_rejected     INTEGER NOT NULL DEFAULT 0,

    -- One entry per rejected item: {"resourceId": "...", "code": "...", "message": "..."}
    errors                  JSONB NOT NULL DEFAULT '[]',

    received_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at            TIMESTAMPTZ
);

CREATE INDEX idx_published_catalogs_txn ON published_catalogs(transaction_id);
CREATE INDEX idx_published_catalogs_bpp ON published_catalogs(bpp_subscriber_id);
CREATE INDEX idx_published_catalogs_status ON published_catalogs(status);
