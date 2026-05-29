"""Planner configuration loaded from environment."""
from __future__ import annotations

import os


# ── LLM ──────────────────────────────────────────────────────
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "llama-3.3-70b-versatile")
LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S", "30"))


# ── Behavior ─────────────────────────────────────────────────
COMPOSE_RETRY_ON_VALIDATION_FAILURE: bool = (
    os.getenv("COMPOSE_RETRY", "true").lower() == "true"
)


# ── Service identity ─────────────────────────────────────────
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "planner")
PLANNER_VERSION: str = os.getenv("PLANNER_VERSION", "2.0.0")
