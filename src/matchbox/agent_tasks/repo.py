"""Agent-task queue persistence (the DAL).

A task is one unit of agent work: a `kind` (extract_reqs | tailor | prep |
draft_followup | thankyou | negotiate | ...), an optional job/application ref, a
free JSON payload, and a lifecycle state: pending -> claimed -> done | failed.

The agent drains via the CLI (`python -m matchbox.agent_tasks`); the SPA reads
and enqueues via /api/agent-tasks. All effects are small, so there is no
separate service layer -- the lifecycle writes live here.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from matchbox.core.db import transaction

VALID_STATES = ("pending", "claimed", "done", "failed")
_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    """One agent_task row -> the JSON shape the agent and the SPA consume."""
    return {
        "id": row["id"],
        "kind": row["kind"],
        "jobId": row["job_id"],
        "applicationId": row["application_id"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "state": row["state"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
        "createdAt": row["created_at"],
        "claimedAt": row["claimed_at"],
        "doneAt": row["done_at"],
    }


def enqueue(
    conn: sqlite3.Connection,
    kind: str,
    *,
    job_id: int | None = None,
    application_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    """Add a pending task. Returns its id."""
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO agent_task (kind, job_id, application_id, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (kind, job_id, application_id, json.dumps(payload or {})),
        )
    return int(cur.lastrowid or 0)


def get(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
    return serialize(row) if row else None


def list_tasks(
    conn: sqlite3.Connection,
    *,
    state: str | None = None,
    kind: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Tasks in FIFO (id) order, optionally filtered by state and/or kind."""
    sql = "SELECT * FROM agent_task"
    where: list[str] = []
    params: list[Any] = []
    if state is not None:
        where.append("state = ?")
        params.append(state)
    if kind is not None:
        where.append("kind = ?")
        params.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [serialize(r) for r in conn.execute(sql, params).fetchall()]


def claim(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    """Claim a task (pending -> claimed). Single-winner: a second claim on an
    already-claimed task is a no-op and returns it unchanged, so two agents
    never process the same task twice."""
    with transaction(conn):
        conn.execute(
            f"UPDATE agent_task SET state='claimed', claimed_at={_NOW} "
            "WHERE id=? AND state='pending'",
            (task_id,),
        )
    return get(conn, task_id)


def complete(
    conn: sqlite3.Connection, task_id: int, *, result: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Mark a task done, recording its result payload."""
    with transaction(conn):
        conn.execute(
            f"UPDATE agent_task SET state='done', done_at={_NOW}, result_json=? WHERE id=?",
            (json.dumps(result) if result is not None else None, task_id),
        )
    return get(conn, task_id)


def fail(conn: sqlite3.Connection, task_id: int, error: str) -> dict[str, Any] | None:
    """Mark a task failed, recording the error."""
    with transaction(conn):
        conn.execute(
            f"UPDATE agent_task SET state='failed', done_at={_NOW}, error=? WHERE id=?",
            (error, task_id),
        )
    return get(conn, task_id)
