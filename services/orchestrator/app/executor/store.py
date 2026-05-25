from __future__ import annotations

import time
from threading import Lock
from typing import Any, Optional

from app.executor.models import ExecutionRecord, ExecutionStatus

_store: dict[str, ExecutionRecord] = {}
_store_lock = Lock()
_TERMINAL = {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED}


def store_create(record: ExecutionRecord) -> None:
    with _store_lock:
        _store[record.execution_id] = record


def store_get(execution_id: str) -> Optional[ExecutionRecord]:
    with _store_lock:
        return _store.get(execution_id)


def store_update(execution_id: str, **kwargs: Any) -> None:
    """Update fields on a record. Terminal states are immutable."""
    with _store_lock:
        record = _store.get(execution_id)
        if record is None:
            return
        if record.status in _TERMINAL:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = time.time()


def store_snapshot() -> list[ExecutionRecord]:
    with _store_lock:
        return list(_store.values())
