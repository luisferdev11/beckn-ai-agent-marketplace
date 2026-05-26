from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from app.executor.state_machine import OrchestratorState


# ── Execution status ─────────────────────────────────────────────────────────

class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── HTTP request / response (Pydantic) ───────────────────────────────────────

class ExecuteRequest(BaseModel):
    plan: dict[str, Any]
    prompt: str
    data: dict[str, Any]


class ExecuteAck(BaseModel):
    execution_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING


class StepSummary(BaseModel):
    step_id: str
    agent: str
    status: str
    attempts: int
    note: Optional[str] = None


class ExecuteResponse(BaseModel):
    execution_id: str
    status: ExecutionStatus
    goal: str
    result: Optional[Any] = None
    execution_summary: list[StepSummary] = []


# ── Internal orchestration record (mutable dataclass) ────────────────────────

@dataclass
class CompletedStep:
    output: Any
    step_note: str
    attempts: int
    timestamp: float


@dataclass
class ErrorEntry:
    step_id: str
    attempt: int
    error: str
    timestamp: float


@dataclass
class ConversationEntry:
    action: str
    step_id: Optional[str]
    timestamp: float
    detail: Any


@dataclass
class OrchestrationRecord:
    execution_id: str
    plan: dict
    prompt: str
    data: dict

    status: ExecutionStatus = ExecutionStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    goal: str = ""
    execution_brief: Optional[dict] = None

    completed_steps: dict[str, CompletedStep] = field(default_factory=dict)
    step_statuses: dict[str, StepStatus] = field(default_factory=dict)
    pending_steps: list[str] = field(default_factory=list)
    current_state: OrchestratorState = OrchestratorState.UNDERSTAND_TASK
    current_layer: int = 0

    error_log: list[ErrorEntry] = field(default_factory=list)
    conversation_log: list[ConversationEntry] = field(default_factory=list)

    result: Optional[Any] = None
    execution_summary: list[dict] = field(default_factory=list)
