"""Artifact DAL: serialize + CRUD for the `artifact` table.

See 007_sota.sql for the exact schema. Uses ``transaction()`` for every write;
camelCase keys on serialize() to match the SPA contract.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.core.db import transaction

VALID_KINDS = ("cv", "cover", "prep", "followup", "thankyou", "counter")
VALID_STATUSES = ("draft", "final", "sent")

# Kinds that trigger the has_draft badge on the parent application row.
_DRAFT_KINDS = frozenset(("followup", "thankyou"))


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    """One artifact row -> camelCase dict for the SPA / CLI."""
    return {
        "id": row["id"],
        "applicationId": row["application_id"],
        "kind": row["kind"],
        "path": row["path"],
        "body": row["body"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def create(
    conn: sqlite3.Connection,
    application_id: int,
    kind: str,
    *,
    path: str | None = None,
    body: str | None = None,
    status: str = "draft",
) -> int:
    """Insert a new artifact row and return its id.

    Raises ``ValueError`` for an invalid ``kind`` or ``status`` before touching
    the DB (belt-and-suspenders over the DB CHECK constraint).

    Side-effect: when ``kind`` is ``"followup"`` or ``"thankyou"``, also sets
    ``application.has_draft = 1`` so the tracker badge lights up.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid kind {kind!r}; must be one of {VALID_KINDS}")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; must be one of {VALID_STATUSES}")

    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO artifact (application_id, kind, path, body, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (application_id, kind, path, body, status),
        )
        artifact_id = int(cur.lastrowid or 0)
        if kind in _DRAFT_KINDS:
            conn.execute(
                "UPDATE application SET has_draft = 1 WHERE id = ?",
                (application_id,),
            )
    return artifact_id


def get(conn: sqlite3.Connection, artifact_id: int) -> dict[str, Any] | None:
    """Fetch a single artifact by id, or None if not found."""
    row = conn.execute("SELECT * FROM artifact WHERE id = ?", (artifact_id,)).fetchone()
    return serialize(row) if row else None


def list_for_app(
    conn: sqlite3.Connection,
    application_id: int,
    *,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    """All artifacts for an application, ordered by id ascending.

    Optionally filter by ``kind``.
    """
    sql = "SELECT * FROM artifact WHERE application_id = ?"
    params: list[Any] = [application_id]
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY id"
    return [serialize(r) for r in conn.execute(sql, params).fetchall()]


def set_status(
    conn: sqlite3.Connection,
    artifact_id: int,
    status: str,
) -> dict[str, Any] | None:
    """Update the status of an artifact and return the updated row.

    Returns ``None`` if the artifact does not exist.
    Raises ``ValueError`` for an invalid status.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; must be one of {VALID_STATUSES}")
    with transaction(conn):
        conn.execute(
            "UPDATE artifact SET status = ? WHERE id = ?",
            (status, artifact_id),
        )
    return get(conn, artifact_id)
