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
