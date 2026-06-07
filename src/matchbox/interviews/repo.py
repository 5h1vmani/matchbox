"""Interview-loop DAL: rounds + debriefs (migration 009).

The only place SQL touches `interview_round` / `debrief`. Serializes to the
design's `Round[]` shape (debrief inlined). Rounds are manual entry; the debrief
is a one-tap honest self-report.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.core.db import transaction

VALID_KINDS = ("recruiter", "hm", "technical", "onsite", "values", "other")
VALID_STATUSES = ("scheduled", "done", "cancelled")
VALID_SENTIMENTS = ("good", "mixed", "tough", "unknown")


def _debrief(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"sentiment": row["sentiment"], "notes": row["notes"], "createdAt": row["created_at"]}


def serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """One round row -> Round view-model, with its debrief inlined."""
    deb = conn.execute(
        "SELECT sentiment, notes, created_at FROM debrief WHERE round_id = ?", (row["id"],)
    ).fetchone()
    return {
        "id": row["id"],
        "applicationId": row["application_id"],
        "kind": row["kind"],
        "scheduledAt": row["scheduled_at"],
        "status": row["status"],
        "focus": row["focus"],
        "debrief": _debrief(deb),
    }


def rounds_for(conn: sqlite3.Connection, application_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM interview_round WHERE application_id = ? "
        "ORDER BY sort_order, COALESCE(scheduled_at, ''), id",
        (application_id,),
    ).fetchall()
    return [serialize(conn, r) for r in rows]


def get_round(conn: sqlite3.Connection, round_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM interview_round WHERE id = ?", (round_id,)).fetchone()
    return serialize(conn, row) if row else None


def create_round(
    conn: sqlite3.Connection,
    application_id: int,
    *,
    kind: str,
    scheduled_at: str | None = None,
    focus: str | None = None,
    status: str = "scheduled",
    sort_order: int = 0,
) -> int:
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid round kind {kind!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO interview_round (application_id, kind, scheduled_at, status, focus, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (application_id, kind, scheduled_at, status, focus, sort_order),
        )
    return int(cur.lastrowid or 0)


def update_round(
    conn: sqlite3.Connection,
    round_id: int,
    *,
    kind: str | None = None,
    scheduled_at: str | None = None,
    focus: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if kind is not None:
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid round kind {kind!r}")
        fields.append("kind = ?")
        values.append(kind)
    if scheduled_at is not None:
        fields.append("scheduled_at = ?")
        values.append(scheduled_at)
    if focus is not None:
        fields.append("focus = ?")
        values.append(focus)
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        fields.append("status = ?")
        values.append(status)
    if fields:
        values.append(round_id)
        with transaction(conn):
            conn.execute(f"UPDATE interview_round SET {', '.join(fields)} WHERE id = ?", values)
    return get_round(conn, round_id)


def delete_round(conn: sqlite3.Connection, round_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM interview_round WHERE id = ?", (round_id,))


def upsert_debrief(
    conn: sqlite3.Connection,
    round_id: int,
    *,
    sentiment: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """One-tap debrief capture (one per round). Marks the round done."""
    if sentiment is not None and sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"invalid sentiment {sentiment!r}")
    with transaction(conn):
        conn.execute(
            "INSERT INTO debrief (round_id, sentiment, notes) VALUES (?, ?, ?) "
            "ON CONFLICT(round_id) DO UPDATE SET sentiment = excluded.sentiment, "
            "notes = excluded.notes",
            (round_id, sentiment, notes),
        )
        conn.execute("UPDATE interview_round SET status = 'done' WHERE id = ?", (round_id,))
    return get_round(conn, round_id)


def prior_debriefs(conn: sqlite3.Connection, application_id: int) -> list[dict[str, Any]]:
    """Debriefs captured so far for an application, oldest first -- the assisted
    context carried into the next prep task. Honest self-report, not statistics."""
    rows = conn.execute(
        """
        SELECT r.kind, r.focus, d.sentiment, d.notes
          FROM debrief d
          JOIN interview_round r ON r.id = d.round_id
         WHERE r.application_id = ?
         ORDER BY r.sort_order, COALESCE(r.scheduled_at, ''), r.id
        """,
        (application_id,),
    ).fetchall()
    return [
        {"kind": r["kind"], "focus": r["focus"], "sentiment": r["sentiment"], "notes": r["notes"]}
        for r in rows
    ]
