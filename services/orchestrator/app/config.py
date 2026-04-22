import os

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "dev-internal-token")
ORCHESTRATOR_VERSION = os.getenv("ORCHESTRATOR_VERSION", "1.0.0")
SERVICE_NAME = os.getenv("SERVICE_NAME", "orchestrator")
