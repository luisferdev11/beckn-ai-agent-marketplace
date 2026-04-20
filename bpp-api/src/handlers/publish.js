const pool = require("../db");
const { sendCallback } = require("../beckn");

// ── Step 1: Save agents to DB ────────────────────────────────────────

async function saveAgentsToDB(agents) {
  const saved = [];

  for (const agent of agents) {
    // Upsert category
    await pool.query(
      `INSERT INTO categories (category_id, display_name)
       VALUES ($1, $2)
       ON CONFLICT (category_id) DO UPDATE SET display_name = $2`,
      [agent.category_id, JSON.stringify(agent.category_display_name)]
    );

    // Upsert provider
    await pool.query(
      `INSERT INTO ai_providers (subscriber_id, bpp_uri, public_key)
       VALUES ($1, $2, $3)
       ON CONFLICT (subscriber_id) DO UPDATE SET bpp_uri = $2, public_key = $3`,
      [agent.provider_subscriber_id, agent.provider_bpp_uri, agent.provider_public_key]
    );

    const { rows: [provider] } = await pool.query(
      `SELECT provider_id FROM ai_providers WHERE subscriber_id = $1`,
      [agent.provider_subscriber_id]
    );

    // Insert agent (new UUIDs auto-generated, no ON CONFLICT on agent_id
    // because we don't know the UUID upfront — duplicates are prevented
    // by checking provider + name before insert)
    const { rows: existing } = await pool.query(
      `SELECT agent_id FROM ai_agents
       WHERE provider_id = $1 AND agent_name->>'en' = $2`,
      [provider.provider_id, agent.agent_name.en]
    );

    let agentId;
    if (existing.length > 0) {
      // Update existing agent
      agentId = existing[0].agent_id;
      await pool.query(
        `UPDATE ai_agents SET
          category_id = $1, access_point_url = $2, interaction_type = $3,
          agent_name = $4, version = $5, capabilities = $6,
          input_schema = $7, output_schema = $8, pricing_model = $9,
          updated_at = NOW()
         WHERE agent_id = $10`,
        [
          agent.category_id, agent.access_point_url, agent.interaction_type || "sync",
          JSON.stringify(agent.agent_name), agent.version, agent.capabilities,
          JSON.stringify(agent.input_schema), JSON.stringify(agent.output_schema),
          JSON.stringify(agent.pricing_model), agentId,
        ]
      );
    } else {
      // Insert new agent
      const { rows: [inserted] } = await pool.query(
        `INSERT INTO ai_agents (
          provider_id, category_id, access_point_url, interaction_type,
          agent_name, version, capabilities, input_schema, output_schema, pricing_model
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
         RETURNING agent_id`,
        [
          provider.provider_id, agent.category_id, agent.access_point_url,
          agent.interaction_type || "sync", JSON.stringify(agent.agent_name),
          agent.version, agent.capabilities, JSON.stringify(agent.input_schema),
          JSON.stringify(agent.output_schema), JSON.stringify(agent.pricing_model),
        ]
      );
      agentId = inserted.agent_id;
    }

    saved.push(agentId);
  }

  return saved;
}

// ── Step 2: Build catalog from DB and publish to Fabric ──────────────

async function publishCatalogToFabric() {
  const { rows: agents } = await pool.query(`
    SELECT
      a.agent_id,
      a.agent_name,
      a.category_id,
      array_to_string(a.capabilities, ', ') AS description,
      a.pricing_model,
      p.provider_id,
      p.subscriber_id AS provider_subscriber_id,
      p.trust_score_aggregate
    FROM ai_agents a
    JOIN ai_providers p ON a.provider_id = p.provider_id
    WHERE a.status = 'active'
  `);

  if (agents.length === 0) {
    throw new Error("No active agents in database to publish");
  }

  // Build Beckn v2.0.0 catalog
  const resources = agents.map((a) => ({
    id: String(a.agent_id),
    descriptor: {
      name: a.agent_name?.en || a.agent_name,
      shortDesc: a.description,
    },
    provider: {
      id: String(a.provider_id),
      descriptor: { name: a.provider_subscriber_id },
    },
    rating: {
      ratingValue: parseFloat(a.trust_score_aggregate) || 0,
      bestRating: 5,
      worstRating: 1,
    },
  }));

  const offers = agents.map((a) => {
    const pricing = a.pricing_model || {};
    return {
      id: `offer-${a.agent_id}`,
      descriptor: {
        name: `${a.agent_name?.en || a.agent_name} — Single Execution`,
        shortDesc: `Pay-per-request — $${pricing.value || 0}/${pricing.type || "request"}`,
      },
      resourceIds: [String(a.agent_id)],
      provider: {
        id: String(a.provider_id),
        descriptor: { name: a.provider_subscriber_id },
      },
    };
  });

  const firstProvider = {
    id: String(agents[0].provider_id),
    descriptor: { name: agents[0].provider_subscriber_id },
  };

  const catalog = {
    id: "CAT-AI-AGENTS-001",
    descriptor: {
      name: "AI Agent Catalog",
      shortDesc: "AI agents published from the marketplace database",
    },
    provider: firstProvider,
    resources,
    offers,
    publishDirectives: { catalogType: "regular" },
  };

  // Send to Fabric via onix-bpp caller
  const context = {
    networkId: "beckn.one/testnet",
    action: "catalog/publish",
    version: "2.0.0",
    bapId: "bap.example.com",
    bapUri: "http://onix-bap:8081/bap/receiver",
    bppId: "bpp.example.com",
    bppUri: "http://onix-bpp:8082/bpp/receiver",
    transactionId: crypto.randomUUID(),
    messageId: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    ttl: "PT30S",
  };

  await sendCallback("publish", context, { catalogs: [catalog] });
  return { agentsPublished: agents.length, catalogId: catalog.id };
}

// ── Endpoint: POST /api/publish ──────────────────────────────────────
// Simulates what the Admin UI would do: register + publish in one action.

async function handlePublish(req, res) {
  const { agents } = req.body;

  if (!agents || !Array.isArray(agents) || agents.length === 0) {
    return res.status(400).json({ error: "Missing or empty 'agents' array" });
  }

  // 1. Save to DB
  let savedIds;
  try {
    savedIds = await saveAgentsToDB(agents);
    console.log(`[publish] Saved ${savedIds.length} agent(s) to DB`);
  } catch (err) {
    console.error("[publish] DB save failed:", err.message);
    return res.status(500).json({ error: "Failed to save agents", detail: err.message });
  }

  // 2. Publish full catalog to Fabric
  try {
    const result = await publishCatalogToFabric();
    console.log(`[publish] Catalog published to Fabric (${result.agentsPublished} agents)`);
    res.json({
      status: "ok",
      db: { agentsSaved: savedIds.length, agentIds: savedIds },
      fabric: { catalogPublished: true, agentsInCatalog: result.agentsPublished },
    });
  } catch (err) {
    console.error("[publish] Fabric publish failed:", err.message);
    res.status(502).json({
      status: "partial",
      db: { agentsSaved: savedIds.length, agentIds: savedIds },
      fabric: { catalogPublished: false, error: err.message },
    });
  }
}

// ── Webhook: on_publish callback from Fabric ─────────────────────────

function handleOnPublish(context, message) {
  console.log("[on_publish] Catalog publish confirmed by Fabric");
  if (message?.error) {
    console.error("[on_publish] Error from Fabric:", message.error);
  }
}

module.exports = { handlePublish, handleOnPublish };
