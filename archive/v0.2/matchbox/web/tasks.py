"""In-process task tracker for background work (bulk tailor today).

A single-process tool doesn't need Celery or RQ. We keep an in-memory dict
keyed by task_id; status is lost on restart, which is acceptable because:
  - Tailor execution is idempotent at the DB level (mark_tailored just
    overwrites the latest paths/cost)
  - Restart is rare (matchbox web is not auto-reloading in normal use)
  - The user can always re-run tailor on incomplete jobs from the inbox

If we ever need persistence, swap this module for a SQLite-backed store —
the public API (start, get, mark_done) is intentionally tiny.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class TaskItem:
    """One unit of work inside a Task (e.g., one job in a bulk tailor)."""

    label: str
    status: Literal["pending", "running", "ok", "failed", "skipped"] = "pending"
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    id: str
    kind: str  # "bulk_tailor" today; reserved for future kinds
    items: list[TaskItem]
    status: TaskStatus = "pending"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items if i.status in ("ok", "failed", "skipped"))

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("done", "failed")


_TASKS: dict[str, Task] = {}
_LOCK = threading.Lock()


def create(kind: str, items: list[TaskItem]) -> Task:
    """Create a new task with `pending` items. Returns the Task object."""
    task = Task(id=str(uuid.uuid4())[:12], kind=kind, items=items)
    with _LOCK:
        _TASKS[task.id] = task
    return task


def get(task_id: str) -> Task | None:
    return _TASKS.get(task_id)


def update_item(task_id: str, idx: int, **fields: Any) -> None:
    with _LOCK:
        t = _TASKS.get(task_id)
        if not t or idx >= len(t.items):
            return
        for k, v in fields.items():
            setattr(t.items[idx], k, v)


def set_status(task_id: str, status: TaskStatus, summary: dict[str, Any] | None = None) -> None:
    with _LOCK:
        t = _TASKS.get(task_id)
        if not t:
            return
        t.status = status
        if status in ("done", "failed"):
            t.completed_at = time.time()
        if summary is not None:
            t.summary = summary


def cleanup_old(max_age_seconds: float = 3600.0) -> int:
    """Drop terminal tasks older than max_age. Returns dropped count."""
    cutoff = time.time() - max_age_seconds
    dropped = 0
    with _LOCK:
        for tid in list(_TASKS):
            t = _TASKS[tid]
            if t.is_terminal and t.completed_at and t.completed_at < cutoff:
                del _TASKS[tid]
                dropped += 1
    return dropped
