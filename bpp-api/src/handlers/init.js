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
    p.subscriber_id       AS provider_name
  FROM ai_agents a
  JOIN ai_providers p ON a.provider_id = p.provider_id
  WHERE a.agent_id = $1`;

async function handleInit(context, message) {
  const resourceId =
    message?.contract?.commitments?.[0]?.resources?.[0]?.id || null;

  let agent = null;
  if (resourceId) {
    const { rows } = await pool.query(AGENT_BY_ID, [resourceId]);
    agent = rows[0] || null;
  }

  if (!agent) {
    const responseContext = buildResponseContext(context, "on_init");
    await sendCallback("on_init", responseContext, {
      error: { code: "40401", message: `Agent not found: ${resourceId}` },
    });
    return;
  }

  // Insert transaction into the user's transactions table
  const messageId = context.messageId || crypto.randomUUID();
  await pool.query(
    `INSERT INTO transactions (context_transaction_id, message_id, agent_id, status)
     VALUES ($1::uuid, $2::uuid, $3, 'pending')`,
    [context.transactionId, messageId, agent.id]
  );

  const price = parseFloat(agent.price_amount) || 0;
  const responseContext = buildResponseContext(context, "on_init");
  await sendCallback("on_init", responseContext, {
    contract: {
      id: `contract-${context.transactionId}`,
      commitments: [
        {
          id: "commitment-001",
          descriptor: { name: agent.name, code: agent.category },
          status: { code: "DRAFT" },
          resources: [
            {
              id: agent.id,
              descriptor: { name: agent.name, code: agent.category },
              quantity: { unitQuantity: 1, unitCode: "EXECUTION" },
            },
          ],
          offer: {
            id: `offer-${agent.id}`,
            resourceIds: [agent.id],
          },
        },
      ],
      participants: message.contract.participants || [],
      performance: [{ id: "perf-001" }],
      settlements: [
        {
          id: "settlement-001",
          status: "DRAFT",
          settlementAttributes: {
            paymentMethod: "PRE_PAID",
            amount: String(price),
            currency: agent.price_currency,
          },
        },
      ],
    },
  });
}

module.exports = handleInit;
