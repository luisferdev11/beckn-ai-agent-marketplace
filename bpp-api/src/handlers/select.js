const pool = require("../db");
const { buildResponseContext, sendCallback } = require("../beckn");

const AGENT_BY_ID = `
  SELECT
    a.agent_id            AS id,
    a.agent_name->>'en'   AS name,
    a.category_id         AS category,
    array_to_string(a.capabilities, ', ') AS description,
    a.pricing_model->>'value'    AS price_amount,
    COALESCE(a.pricing_model->>'currency', 'USD') AS price_currency,
    p.provider_id,
    p.subscriber_id       AS provider_name,
    p.trust_score_aggregate AS trust_score
  FROM ai_agents a
  JOIN ai_providers p ON a.provider_id = p.provider_id
  WHERE a.agent_id = $1`;

async function handleSelect(context, message) {
  const resourceId =
    message?.contract?.commitments?.[0]?.resources?.[0]?.id || null;

  let agent = null;
  if (resourceId) {
    const { rows } = await pool.query(AGENT_BY_ID, [resourceId]);
    agent = rows[0] || null;
  }

  if (!agent) {
    const responseContext = buildResponseContext(context, "on_select");
    await sendCallback("on_select", responseContext, {
      error: { code: "40401", message: `Agent not found: ${resourceId}` },
    });
    return;
  }

  const price = parseFloat(agent.price_amount) || 0;
  const responseContext = buildResponseContext(context, "on_select");
  await sendCallback("on_select", responseContext, {
    contract: {
      id: `contract-${context.transactionId}`,
      participants: message.contract.participants || [],
      commitments: [
        {
          id: "commitment-001",
          descriptor: {
            name: agent.name,
            code: agent.category,
            shortDesc: agent.description,
          },
          status: { code: "DRAFT" },
          resources: [
            {
              id: agent.id,
              descriptor: {
                name: agent.name,
                code: agent.category,
                shortDesc: agent.description,
              },
              quantity: { unitQuantity: 1, unitCode: "EXECUTION" },
            },
          ],
          offer: {
            id: `offer-${agent.id}`,
            resourceIds: [agent.id],
          },
        },
      ],
      consideration: [
        {
          id: "consideration-001",
          price: { currency: agent.price_currency, value: String(price) },
          status: { code: "DRAFT" },
          breakup: [
            {
              title: "Agent Execution Fee",
              price: { currency: agent.price_currency, value: String(price) },
            },
          ],
        },
      ],
    },
  });
}

module.exports = handleSelect;
