"""Hybrid store: in-memory for active executions, Redis for persistence and TTL.

Records live in-memory while RUNNING (fast mutations). On terminal state
(COMPLETED/PARTIAL/FAILED) they are serialized to Redis with a TTL so they
auto-expire. On startup the in-memory cache is empty, but finished records
can still be fetched from Redis.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

from app.config import RECORD_TTL_SECONDS, REDIS_URL
from app.executor.models import (
    CompletedStep,
    ConversationEntry,
    ErrorEntry,
    ExecutionStatus,
    OrchestrationRecord,
    StepStatus,
)
from app.executor.state_machine import OrchestratorState

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "orch2:exec:"
_TERMINAL = {ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL, ExecutionStatus.FAILED}

# ── In-memory cache (active executions only) ─────────────────────────────────
_mem: dict[str, OrchestrationRecord] = {}
_lock = asyncio.Lock()

# ── Redis connection (lazy init) ─────────────────────────────────────────────
_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ── Serialization ────────────────────────────────────────────────────────────

def _serialize_record(record: OrchestrationRecord) -> str:
    """Serialize OrchestrationRecord to JSON string for Redis."""
    data = {
        "execution_id": record.execution_id,
        "plan": record.plan,
        "prompt": record.prompt,
        "data": record.data,
        "status": record.status.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "goal": record.goal,
        "execution_brief": record.execution_brief,
        "completed_steps": {
            sid: dataclasses.asdict(cs) for sid, cs in record.completed_steps.items()
        },
        "step_statuses": {k: v.value for k, v in record.step_statuses.items()},
        "pending_steps": record.pending_steps,
        "current_state": record.current_state.value,
        "current_layer": record.current_layer,
        "error_log": [dataclasses.asdict(e) for e in record.error_log],
        "conversation_log": [dataclasses.asdict(c) for c in record.conversation_log],
        "result": record.result,
        "execution_summary": record.execution_summary,
    }
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize_record(raw: str) -> OrchestrationRecord:
    """Deserialize JSON string from Redis back to OrchestrationRecord."""
    d = json.loads(raw)
    record = OrchestrationRecord(
        execution_id=d["execution_id"],
        plan=d["plan"],
        prompt=d["prompt"],
        data=d["data"],
    )
    record.status = ExecutionStatus(d["status"])
    record.created_at = d["created_at"]
    record.updated_at = d["updated_at"]
    record.goal = d.get("goal", "")
    record.execution_brief = d.get("execution_brief")
    record.current_state = OrchestratorState(d.get("current_state", "DELIVER_RESULT"))
    record.current_layer = d.get("current_layer", 0)
    record.pending_steps = d.get("pending_steps", [])
    record.result = d.get("result")
    record.execution_summary = d.get("execution_summary", [])

    record.step_statuses = {
        k: StepStatus(v) for k, v in d.get("step_statuses", {}).items()
    }
    record.completed_steps = {
        sid: CompletedStep(**cs) for sid, cs in d.get("completed_steps", {}).items()
    }
    record.error_log = [ErrorEntry(**e) for e in d.get("error_log", [])]
    record.conversation_log = [ConversationEntry(**c) for c in d.get("conversation_log", [])]

    return record


# ── Public API (same interface as before) ────────────────────────────────────

async def store_create(record: OrchestrationRecord) -> None:
    async with _lock:
        _mem[record.execution_id] = record


async def store_get(execution_id: str) -> Optional[OrchestrationRecord]:
    async with _lock:
        record = _mem.get(execution_id)
        if record is not None:
            return record

    # Not in memory — check Redis (finished executions)
    try:
        r = await _get_redis()
        raw = await r.get(f"{_REDIS_PREFIX}{execution_id}")
        if raw:
            return _deserialize_record(raw)
    except Exception as exc:
        logger.warning("Redis read failed for %s: %s", execution_id, exc)

    return None


async def store_update(execution_id: str, **kwargs: Any) -> None:
    async with _lock:
        record = _mem.get(execution_id)
        if record is None:
            return
        if record.status in _TERMINAL:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = time.time()

        # If terminal, persist to Redis and remove from memory
        if record.status in _TERMINAL:
            await _persist_to_redis(record)
            del _mem[execution_id]


async def store_snapshot() -> list[OrchestrationRecord]:
    """Return all known records (in-memory + Redis)."""
    async with _lock:
        records = list(_mem.values())

    try:
        r = await _get_redis()
        keys = []
        async for key in r.scan_iter(f"{_REDIS_PREFIX}*"):
            keys.append(key)
        if keys:
            values = await r.mget(keys)
            for raw in values:
                if raw:
                    rec = _deserialize_record(raw)
                    # Don't duplicate if somehow still in memory
                    if rec.execution_id not in {r.execution_id for r in records}:
                        records.append(rec)
    except Exception as exc:
        logger.warning("Redis snapshot failed: %s", exc)

    return records


# ── Internal ─────────────────────────────────────────────────────────────────

async def _persist_to_redis(record: OrchestrationRecord) -> None:
    """Write a finished record to Redis with TTL."""
    try:
        r = await _get_redis()
        key = f"{_REDIS_PREFIX}{record.execution_id}"
        await r.set(key, _serialize_record(record), ex=RECORD_TTL_SECONDS)
        logger.info("Persisted %s to Redis (TTL=%ds)", record.execution_id, RECORD_TTL_SECONDS)
    except Exception as exc:
        logger.error("Failed to persist %s to Redis: %s", record.execution_id, exc)
