from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from app.executor.models import ExecutionStatus, OrchestrationRecord

_store: dict[str, OrchestrationRecord] = {}
_lock = asyncio.Lock()

_TERMINAL = {ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL, ExecutionStatus.FAILED}


async def store_create(record: OrchestrationRecord) -> None:
    async with _lock:
        _store[record.execution_id] = record


async def store_get(execution_id: str) -> Optional[OrchestrationRecord]:
    async with _lock:
        return _store.get(execution_id)


async def store_update(execution_id: str, **kwargs: Any) -> None:
    async with _lock:
        record = _store.get(execution_id)
        if record is None:
            return
        if record.status in _TERMINAL:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = time.time()


async def store_snapshot() -> list[OrchestrationRecord]:
    async with _lock:
        return list(_store.values())
