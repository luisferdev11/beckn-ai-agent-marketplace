const express = require("express");
const pool = require("./db");
const handleDiscover = require("./handlers/discover");
const handleSelect = require("./handlers/select");
const handleInit = require("./handlers/init");
const handleConfirm = require("./handlers/confirm");
const { handlePublish, handleOnPublish } = require("./handlers/publish");

const app = express();
const PORT = process.env.PORT || 3002;

app.use(express.json({ limit: "5mb" }));

app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  next();
});

app.get("/api/health", async (_req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok", service: "bpp-ai-agent-marketplace", db: "connected" });
  } catch {
    res.status(503).json({ status: "error", service: "bpp-ai-agent-marketplace", db: "disconnected" });
  }
});

const handlers = {
  discover: handleDiscover,
  select: handleSelect,
  init: handleInit,
  confirm: handleConfirm,
  on_publish: handleOnPublish,
};

// ── Publish endpoint (BPP admin) ──────────────────────────────────────
// Saves agents to DB, then publishes full catalog to Fabric via ONIX.
app.post("/api/publish", handlePublish);

app.post("/api/webhook", async (req, res) => {
  const { context, message } = req.body;

  if (!context?.action) {
    return res.status(400).json({
      message: { ack: { status: "NACK" } },
      error: { code: "40001", message: "Missing context.action" },
    });
  }

  const action = context.action;
  console.log(`[webhook] Received action: ${action} | txnId: ${context.transactionId}`);

  const handler = handlers[action];
  if (!handler) {
    console.log(`[webhook] Unsupported action: ${action} — returning ACK (no-op)`);
    return res.json({ message: { ack: { status: "ACK" } } });
  }

  res.json({ message: { ack: { status: "ACK" } } });

  try {
    await handler(context, message);
  } catch (err) {
    console.error(`[webhook] Error handling ${action}:`, err.message);
  }
});

app.get("/api/agents", async (_req, res) => {
  const { rows } = await pool.query(
    `SELECT
       a.agent_id            AS id,
       a.agent_name->>'en'   AS name,
       a.category_id         AS category,
       array_to_string(a.capabilities, ', ') AS description,
       a.pricing_model->>'value'    AS price_amount,
       COALESCE(a.pricing_model->>'currency', 'USD') AS price_currency,
       a.pricing_model->>'type'     AS pricing_type,
       a.access_point_url,
       a.status,
       p.provider_id,
       p.subscriber_id       AS provider_name,
       p.trust_score_aggregate AS trust_score
     FROM ai_agents a
     JOIN ai_providers p ON a.provider_id = p.provider_id`
  );
  res.json(rows);
});

app.get("/api/transactions", async (_req, res) => {
  const { rows } = await pool.query(
    "SELECT * FROM transactions ORDER BY created_at DESC"
  );
  res.json(rows);
});

app.listen(PORT, () => {
  console.log(`[bpp-api] AI Agent Marketplace BPP listening on port ${PORT}`);
  console.log(`[bpp-api] Webhook: http://localhost:${PORT}/api/webhook`);
  console.log(`[bpp-api] Health:  http://localhost:${PORT}/api/health`);
  console.log(`[bpp-api] Agents:  http://localhost:${PORT}/api/agents`);
});
