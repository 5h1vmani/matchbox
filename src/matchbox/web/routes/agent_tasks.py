"""JSON API for the agent-task queue (prefix /api/agent-tasks).

The dashboard enqueues intents and watches their state here; the agent drains
them via the CLI (`python -m matchbox.agent_tasks`). See agent_tasks/repo.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.agent_tasks import repo
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/agent-tasks")


class EnqueueBody(BaseModel):
    kind: str
    jobId: int | None = None
    applicationId: int | None = None
    payload: dict[str, Any] | None = None


@router.get("")
def list_tasks(
    conn: ConnDep, state: str | None = None, kind: str | None = None
) -> list[dict[str, Any]]:
    """Tasks in FIFO order. `state` defaults to all; pass ?state=pending for the
    drain queue, or ?state=claimed to see what the agent is working on."""
    return repo.list_tasks(conn, state=state, kind=kind)


@router.get("/{task_id}")
def get_task(task_id: int, conn: ConnDep) -> dict[str, Any]:
    task = repo.get(conn, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@router.post("")
def enqueue(body: EnqueueBody, conn: ConnDep) -> dict[str, Any]:
    task_id = repo.enqueue(
        conn,
        body.kind,
        job_id=body.jobId,
        application_id=body.applicationId,
        payload=body.payload,
    )
    created = repo.get(conn, task_id)
    assert created is not None  # just inserted
    return created
