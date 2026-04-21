"""
BPP service configuration.

All config comes from environment variables with sensible defaults
for the Docker Compose development environment.
"""

import json
import os

PORT = int(os.getenv("PORT", "3002"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "bpp-ai")

# URL of ONIX-BPP caller — where we send on_* callbacks
BPP_CALLBACK_URL = os.getenv("BPP_CALLBACK_URL", "http://onix-bpp:8082/bpp/caller")

# URL of the orchestrator service — where we delegate agent execution
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:3003")

# Maps agent_id → agent service URL. Populated via env var or defaults.
# Format: JSON object e.g. '{"agent-summarizer-001":"http://agents:3004"}'
_default_agent_urls = {
    "agent-summarizer-001": "http://agents:3004",
    "agent-code-reviewer-001": "http://agents:3004",
    "agent-data-extractor-001": "http://agents:3004",
}
AGENT_URL_MAP: dict[str, str] = json.loads(os.getenv("AGENT_URL_MAP", "{}")) or _default_agent_urls

# Beckn identity (matches ONIX config and DeDi registry)
BPP_ID = os.getenv("BPP_ID", "bpp.example.com")
BPP_URI = os.getenv("BPP_URI", "http://onix-bpp:8082/bpp/receiver")
NETWORK_ID = os.getenv("NETWORK_ID", "beckn.one/testnet")
