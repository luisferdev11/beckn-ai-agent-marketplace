import os

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "dev-internal-token")
ORCHESTRATOR_VERSION = os.getenv("ORCHESTRATOR_VERSION", "2.0.0")
SERVICE_NAME = os.getenv("SERVICE_NAME", "orchestrator2")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")
RECORD_TTL_SECONDS = int(os.getenv("RECORD_TTL_SECONDS", "3600"))  # 1 hour

# Agent call resilience
AGENT_MAX_RETRIES = 3
AGENT_BACKOFF_SECONDS = [1, 2, 4]
VALIDATION_MAX_RETRIES = 2
LLM_MAX_RETRIES = 2
LLM_RETRY_WAIT = 1
