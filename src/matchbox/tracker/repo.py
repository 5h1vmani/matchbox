"""Tracker persistence + serialization (the DAL).

Loads `application` rows joined to their `job`, fetches child rows, and
serializes to the exact view-model the SPA consumes (relative `daysAgo`, the
`nextAction` object, monogram colours, derived `stale`). Keeps SQL in one place.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.core.db import PROJECT_ROOT, transaction
from matchbox.tracker import rules

_APP_SELECT = """
  SELECT a.id, a.job_id, a.run_id, a.stage, a.salary, a.source, a.starred, a.has_draft,
         a.applied_at, a.updated_at, a.next_action, a.next_action_kind,
         a.next_action_at, a.next_action_time, a.cv_path, a.cover_path,
         j.company, j.title AS role, j.location AS location,
         j.url AS job_url, j.apply_url AS apply_url
    FROM application a
    JOIN job j ON j.id = a.job_id
"""


def _next_action(row: sqlite3.Row) -> dict[str, Any] | None:
    label = row["next_action"]
    if not label:
        return None
    na: dict[str, Any] = {
        "kind": row["next_action_kind"] or "followup",
        "label": label,
        "due": rules.due_from(row["next_action_at"]),
    }
    if row["next_action_time"]:
        na["time"] = row["next_action_time"]
    return na


def _children(
    conn: sqlite3.Connection, app_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    events = [
        {"daysAgo": rules.days_since(r["created_at"]) or 0, "kind": r["kind"], "text": r["text"]}
        for r in conn.execute(
            "SELECT kind, text, created_at FROM app_event WHERE application_id=? "
            "ORDER BY datetime(created_at) DESC, id DESC",
            (app_id,),
        )
    ]
    notes = [
        {"daysAgo": rules.days_since(r["created_at"]) or 0, "text": r["text"]}
        for r in conn.execute(
            "SELECT text, created_at FROM app_note WHERE application_id=? "
            "ORDER BY datetime(created_at) DESC, id DESC",
            (app_id,),
        )
    ]
    contacts = [
        {
            "name": r["name"],
            "role": r["role"] or "",
            "initials": r["initials"] or (r["name"][:1] if r["name"] else ""),
        }
        for r in conn.execute(
            "SELECT name, role, initials FROM app_contact WHERE application_id=? ORDER BY id",
            (app_id,),
        )
    ]
    return events, notes, contacts


def _cv_url(conn: sqlite3.Connection, app_id: int, job_id: int, cv_path: str | None) -> str | None:
    """Resolve the served CV link: the stamped cv_path first, else the newest
    run output on disk (apps queued before a later re-tailor keep a stale or
    empty cv_path while runs/<id>/output/<job>/cv.pdf exists)."""
    if cv_path and (PROJECT_ROOT / cv_path).is_file():
        return f"/api/applications/{app_id}/cv"
    for r in conn.execute(
        "SELECT run_id FROM run_job WHERE job_id=? ORDER BY run_id DESC", (job_id,)
    ):
        if (PROJECT_ROOT / "runs" / r["run_id"] / "output" / str(job_id) / "cv.pdf").is_file():
            return f"/runs/{r['run_id']}/output/{job_id}/cv.pdf"
    return None


def serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    app_id = row["id"]
    events, notes, contacts = _children(conn, app_id)
    na = _next_action(row)
    updated_days = rules.days_since(row["updated_at"]) or 0
    stage = row["stage"] or "saved"
    return {
        "id": str(app_id),
        "company": row["company"],
        "role": row["role"],
        "location": row["location"] or "",
        "salary": row["salary"] or "",
        "source": row["source"] or "",
        "stage": stage,
        "appliedDaysAgo": rules.days_since(row["applied_at"]),
        "updatedDaysAgo": updated_days,
        "nextAction": na,
        "hasDraft": bool(row["has_draft"]),
        "events": events,
        "contacts": contacts,
        "notes": notes,
        "starred": bool(row["starred"]),
        "mono": rules.mono_for(row["company"]),
        "stale": rules.is_stale(stage, na["due"] if na else None, updated_days),
        "jobId": row["job_id"],
        "runId": row["run_id"],
        "jobUrl": row["apply_url"] or row["job_url"] or None,
        "cvUrl": _cv_url(conn, app_id, row["job_id"], row["cv_path"]),
    }


def load_apps(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(_APP_SELECT + " ORDER BY a.id").fetchall()
    return [serialize(conn, r) for r in rows]


def load_one(conn: sqlite3.Connection, app_id: int) -> dict[str, Any] | None:
    row = raw(conn, app_id)
    return serialize(conn, row) if row else None


def raw(conn: sqlite3.Connection, app_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(_APP_SELECT + " WHERE a.id=?", (app_id,)).fetchone()
    return row


def update_app(conn: sqlite3.Connection, app_id: int, **fields: Any) -> None:
    """Update scalar columns on the application row. Keys are trusted column names."""
    if not fields:
        return
    assignments = ", ".join(f"{k}=?" for k in fields)
    with transaction(conn):
        conn.execute(f"UPDATE application SET {assignments} WHERE id=?", (*fields.values(), app_id))


def add_event(
    conn: sqlite3.Connection, app_id: int, kind: str, text: str, bump: bool = True
) -> None:
    """Append a history event; by default also stamps updated_at = now."""
    with transaction(conn):
        conn.execute(
            "INSERT INTO app_event (application_id, kind, text) VALUES (?,?,?)",
            (app_id, kind, text),
        )
        if bump:
            conn.execute(
                "UPDATE application SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (app_id,),
            )


def add_note(conn: sqlite3.Connection, app_id: int, text: str) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO app_note (application_id, text) VALUES (?,?)", (app_id, text))
