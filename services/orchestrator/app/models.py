from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ── HTTP request/response (Pydantic) ────────────────────────────────────────

class ExecuteRequest(BaseModel):
    contract_id: str
    agent_id: str
    agent_url: str
    input: dict[str, Any]
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    timeout_ms: int = 30000


class ExecuteAck(BaseModel):
    execution_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING


class TokensUsed(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class ExecutionMetadata(BaseModel):
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    latency_ms: Optional[int] = None
    tokens_used: Optional[TokensUsed] = None
    model: Optional[str] = None


class ExecuteResponse(BaseModel):
    execution_id: str
    contract_id: str
    agent_id: str
    status: ExecutionStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: ExecutionMetadata


# ── Internal agent wire format (POST /task) ─────────────────────────────────
# Request: flat dict defined by each agent team (no wrapper)
# Response: fixed envelope so the orchestrator can parse status/usage

class ErrorModel(BaseModel):
    code: str
    message: str


class UsageModel(BaseModel):
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class TaskResponse(BaseModel):
    status: str  # "success" | "error"
    result: Optional[Any] = None
    error: Optional[ErrorModel] = None
    usage: UsageModel


# ── In-memory execution record (mutable dataclass) ──────────────────────────

@dataclass
class ExecutionRecord:
    execution_id: str
    contract_id: str
    agent_id: str
    agent_url: str
    input: dict
    input_schema: Optional[dict]
    output_schema: Optional[dict]
    timeout_ms: int
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Any] = None
    error_message: Optional[str] = None
    usage: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    updated_at: Optional[float] = None
