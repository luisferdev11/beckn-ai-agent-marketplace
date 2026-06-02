"""
BPP service configuration.

All config comes from environment variables with sensible defaults
for the Docker Compose development environment.
"""

import os

PORT = int(os.getenv("PORT", "3002"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "bpp-ai")

# URL of ONIX-BPP caller — where we send on_* callbacks
BPP_CALLBACK_URL = os.getenv("BPP_CALLBACK_URL", "http://onix-bpp:8082/bpp/caller")

# URL of the orchestrator service — where we delegate agent execution
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:3003")

# URL of orchestrator v2 — multi-agent pipeline execution
ORCHESTRATOR2_URL = os.getenv("ORCHESTRATOR2_URL", "http://orchestrator2:3008")

# URL of the marketplace CDS — where we POST rating ingest events so the
# discover quality component reflects new ratings without us writing
# directly to the CDS database (deliberate separation of concerns).
CDS_BASE_URL = os.getenv("CDS_BASE_URL", "http://mock-network:8090")

# Beckn identity (matches ONIX config and DeDi registry)
BPP_ID = os.getenv("BPP_ID", "bpp.example.com")
BPP_URI = os.getenv("BPP_URI", "http://onix-bpp:8082/bpp/receiver")
NETWORK_ID = os.getenv("NETWORK_ID", "beckn.one/testnet")
