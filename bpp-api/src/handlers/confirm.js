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
    a.access_point_url,
    p.provider_id,
    p.subscriber_id       AS provider_name
  FROM ai_agents a
  JOIN ai_providers p ON a.provider_id = p.provider_id
  WHERE a.agent_id = $1`;

async function handleConfirm(context, message) {
  const resourceId =
    message?.contract?.commitments?.[0]?.resources?.[0]?.id || null;

  let agent = null;
  if (resourceId) {
    const { rows } = await pool.query(AGENT_BY_ID, [resourceId]);
    agent = rows[0] || null;
  }

  if (!agent) {
    const responseContext = buildResponseContext(context, "on_confirm");
    await sendCallback("on_confirm", responseContext, {
      error: { code: "40401", message: `Agent not found: ${resourceId}` },
    });
    return;
  }

  const userInput =
    message?.contract?.commitments?.[0]?.resources?.[0]?.descriptor?.userInput ||
    message?.contract?.commitments?.[0]?.resources?.[0]?.descriptor?.longDesc ||
    message?.userInput ||
    message?.input ||
    "No input provided";

  // Mark transaction as pending with the request payload
  await pool.query(
    `UPDATE transactions
     SET status = 'pending', request_payload = $1::jsonb
     WHERE context_transaction_id = $2::uuid AND agent_id = $3`,
    [JSON.stringify({ input: userInput }), context.transactionId, agent.id]
  );

  // ====== LLM INTEGRATION POINT ======
  const llmOutput = await callLLM(agent, userInput);
  // ====================================

  // Mark transaction as completed with the response payload
  await pool.query(
    `UPDATE transactions
     SET status = 'completed',
         response_payload = $1::jsonb,
         completed_at = NOW()
     WHERE context_transaction_id = $2::uuid AND agent_id = $3`,
    [JSON.stringify({ output: llmOutput }), context.transactionId, agent.id]
  );

  const responseContext = buildResponseContext(context, "on_confirm");
  await sendCallback("on_confirm", responseContext, {
    contract: {
      id: `contract-${context.transactionId}`,
      commitments: [
        {
          id: "commitment-001",
          descriptor: { name: agent.name, code: agent.category },
          status: { code: "ACTIVE" },
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
      performance: [
        {
          id: "perf-001",
          performanceAttributes: {
            executionStatus: "COMPLETED",
            output: llmOutput,
            category: agent.category,
            agentId: agent.id,
          },
        },
      ],
      settlements: [{ id: "settlement-001", status: "COMPLETE" }],
    },
  });
}

async function callLLM(agent, userInput) {
  console.log(`[llm] Agent "${agent.name}" (${agent.category}) processing input...`);

  // TODO: Replace with real LLM API call
  return `[MOCK RESPONSE from ${agent.name} using ${agent.category}]\n\n`
    + `Simulated response for: "${userInput.substring(0, 100)}..."\n\n`
    + `Agent: ${agent.name}\nCategory: ${agent.category}\nModel: ${agent.category}`;
}

module.exports = handleConfirm;
