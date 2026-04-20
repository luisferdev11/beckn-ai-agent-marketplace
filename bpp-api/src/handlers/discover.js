const pool = require("../db");
const { buildResponseContext, sendCallback } = require("../beckn");

const AGENT_QUERY = `
  SELECT
    a.agent_id            AS id,
    a.agent_name->>'en'   AS name,
    a.category_id         AS category,
    array_to_string(a.capabilities, ', ') AS description,
    a.pricing_model->>'value'    AS price_amount,
    COALESCE(a.pricing_model->>'currency', 'USD') AS price_currency,
    a.pricing_model->>'type'     AS pricing_type,
    a.access_point_url,
    a.interaction_type,
    p.provider_id,
    p.subscriber_id       AS provider_name,
    p.trust_score_aggregate AS trust_score
  FROM ai_agents a
  JOIN ai_providers p ON a.provider_id = p.provider_id
  WHERE a.status = 'active'`;

async function handleDiscover(context, message) {
  let keyword = "";
  if (message?.intent?.filters?.expression) keyword = message.intent.filters.expression;
  if (message?.intent?.query) keyword = message.intent.query;
  if (message?.intent?.descriptor?.name) keyword = message.intent.descriptor.name;
  if (message?.intent?.search) keyword = message.intent.search;

  let agents;
  if (keyword) {
    const search = `%${keyword}%`;
    const { rows } = await pool.query(
      `${AGENT_QUERY}
        AND (a.agent_name->>'en' ILIKE $1
             OR a.category_id ILIKE $2
             OR array_to_string(a.capabilities, ', ') ILIKE $3)`,
      [search, search, search]
    );
    agents = rows;
  }

  if (!agents || agents.length === 0) {
    const { rows } = await pool.query(AGENT_QUERY);
    agents = rows;
  }

  const resources = agents.map((agent) => ({
    id: agent.id,
    descriptor: {
      name: agent.name,
      code: agent.category,
      shortDesc: agent.description,
    },
    tags: [
      { descriptor: { code: "interaction_type" }, value: agent.interaction_type || "sync" },
      { descriptor: { code: "trust_score" }, value: String(agent.trust_score) },
      { descriptor: { code: "provider" }, value: agent.provider_name },
      { descriptor: { code: "provider_id" }, value: agent.provider_id },
    ],
    quantity: { unitQuantity: 1, unitCode: "EXECUTION" },
  }));

  const offers = agents.map((agent) => ({
    id: `offer-${agent.id}`,
    descriptor: {
      name: `${agent.name} — Single Execution`,
      code: agent.category,
    },
    resourceIds: [agent.id],
    offerAttributes: {
      priceSpecification: {
        currency: agent.price_currency,
        price: parseFloat(agent.price_amount) || 0,
      },
    },
  }));

  const responseContext = buildResponseContext(context, "on_discover");
  await sendCallback("on_discover", responseContext, {
    catalog: {
      descriptor: { name: "AI Agent Marketplace" },
      resources,
      offers,
    },
  });
}

module.exports = handleDiscover;
