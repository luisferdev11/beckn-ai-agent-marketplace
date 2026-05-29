"""BAP service configuration."""

import os

PORT = int(os.getenv("PORT", "3001"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "bap-ai")

# URL of ONIX-BAP caller — where we send Beckn actions (select, init, confirm...)
BAP_CALLER_URL = os.getenv("BAP_CALLER_URL", "http://onix-bap:8081/bap/caller")

# Beckn identity (matches ONIX config and DeDi registry)
BAP_ID = os.getenv("BAP_ID", "bap.example.com")
BAP_URI = os.getenv("BAP_URI", "http://onix-bap:8081/bap/receiver")
BPP_ID = os.getenv("BPP_ID", "bpp.example.com")
BPP_URI = os.getenv("BPP_URI", "http://onix-bpp:8082/bpp/receiver")
NETWORK_ID = os.getenv("NETWORK_ID", "beckn.one/testnet")

# ── Planning ─────────────────────────────────────────────────
# URL of the LLM planner service (separate microservice, port 3010 by default).
PLANNER_URL = os.getenv("PLANNER_URL", "http://planner:3010")

# Rate limit applied to POST /api/plan. Format follows slowapi syntax
# ("N/period"). Each /plan call burns LLM tokens — this prevents abuse.
PLAN_RATE_LIMIT = os.getenv("PLAN_RATE_LIMIT", "10/minute")

# How long to wait for an on_discover callback before giving up on a skill.
DISCOVER_TIMEOUT_S = float(os.getenv("DISCOVER_TIMEOUT_S", "10"))

# How long the planner LLM endpoints may take (per call).
PLANNER_TIMEOUT_S = float(os.getenv("PLANNER_TIMEOUT_S", "60"))
