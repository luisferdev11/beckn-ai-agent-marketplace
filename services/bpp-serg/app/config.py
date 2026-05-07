"""
BPP-Serg service configuration.

All config comes from environment variables with sensible defaults
for the Docker Compose development environment.

Agent routing (which agent_id maps to which agent runtime URL) is read
from a YAML file pointed to by AGENT_ROUTING_FILE. Falls back to the
legacy AGENT_URL_MAP env-var-as-JSON for backwards compatibility.
"""

import json
import logging
import os

import yaml


logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "3005"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "bpp-serg")

BPP_CALLBACK_URL = os.getenv("BPP_CALLBACK_URL", "http://onix-bpp-serg:8083/bpp/caller")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:3003")

BPP_ID = os.getenv("BPP_ID", "bpp-serg.example.com")
BPP_URI = os.getenv("BPP_URI", "http://onix-bpp-serg:8083/bpp/receiver")
NETWORK_ID = os.getenv("NETWORK_ID", "beckn.one/testnet")


def _load_agent_routing() -> dict[str, str]:
    """
    Load AGENT_URL_MAP from YAML if AGENT_ROUTING_FILE is set, else from
    the legacy JSON env var, else from defaults.
    """
    routing_path = os.getenv("AGENT_ROUTING_FILE")
    if routing_path and os.path.exists(routing_path):
        with open(routing_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        agents = data.get("agents") or {}
        if isinstance(agents, dict) and agents:
            logger.info("loaded agent routing from %s — %d entries", routing_path, len(agents))
            return dict(agents)

    legacy = os.getenv("AGENT_URL_MAP")
    if legacy:
        parsed = json.loads(legacy)
        if parsed:
            logger.info("loaded agent routing from AGENT_URL_MAP env var — %d entries", len(parsed))
            return parsed

    logger.info("agent routing falling back to bpp-serg defaults")
    return {
        "summarizer-v1":     "http://agents-serg:3006",
        "extractor-v1":      "http://agents-serg:3006",
        "code-reviewer-v1":  "http://agents-serg:3006",
        "translator-v1":     "http://agents-serg:3006",
        "email-writer-v1":   "http://agents-serg:3006",
        "sentiment-v1":      "http://agents-serg:3006",
    }


AGENT_URL_MAP: dict[str, str] = _load_agent_routing()
