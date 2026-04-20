const axios = require("axios");

const ONIX_BPP_CALLER = process.env.ONIX_BPP_CALLER || "http://onix-bpp:8082/bpp/caller";

/**
 * Build a Beckn on_* response context from the incoming request context.
 */
function buildResponseContext(incomingContext, onAction) {
  return {
    networkId: incomingContext.networkId,
    action: onAction,
    version: incomingContext.version || "2.0.0",
    bapId: incomingContext.bapId,
    bapUri: incomingContext.bapUri,
    bppId: incomingContext.bppId,
    bppUri: incomingContext.bppUri,
    transactionId: incomingContext.transactionId,
    messageId: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    ttl: "PT30S",
  };
}

/**
 * Send a callback (on_*) through the ONIX BPP caller adapter.
 */
async function sendCallback(onAction, context, message) {
  const url = `${ONIX_BPP_CALLER}/${onAction}`;
  const payload = { context, message };

  console.log(`[beckn] POST ${url}`);
  console.log(`[beckn] payload:`, JSON.stringify(payload, null, 2));

  try {
    const res = await axios.post(url, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 10000,
    });
    console.log(`[beckn] ${onAction} callback sent — status ${res.status}`);
    return res.data;
  } catch (err) {
    console.error(`[beckn] ${onAction} callback failed:`, err.message);
    throw err;
  }
}

module.exports = { buildResponseContext, sendCallback };
