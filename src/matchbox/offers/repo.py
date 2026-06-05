"""Offer DAL — serialize + CRUD for the `offer` table.

The offer table is created by migration 007 (src/matchbox/core/007_sota.sql).
All writes use transaction(); reads are plain SELECTs.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from matchbox.core.db import transaction

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"

VALID_STATUSES = ("received", "negotiating", "accepted", "declined")

_MUTABLE_FIELDS = frozenset(
    {"base", "bonus", "equity", "currency", "location", "received_at", "status", "notes"}
)


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    """One offer row -> the JSON shape consumed by the SPA and CLI."""
    base: float | None = row["base"]
    bonus: float | None = row["bonus"]
    total_comp: float | None = (base + (bonus or 0.0)) if base is not None else None
    return {
        "id": row["id"],
        "applicationId": row["application_id"],
        "base": base,
        "bonus": bonus,
        "equity": row["equity"],
        "currency": row["currency"],
        "location": row["location"],
        "receivedAt": row["received_at"],
        "status": row["status"],
        "notes": row["notes"],
        "createdAt": row["created_at"],
        "totalComp": total_comp,
    }


def create(
    conn: sqlite3.Connection,
    application_id: int,
    *,
    base: float | None = None,
    bonus: float | None = None,
    equity: str | None = None,
    currency: str | None = None,
    location: str | None = None,
    received_at: str | None = None,
    notes: str | None = None,
) -> int:
    """Insert a new offer and return its id."""
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO offer "
            "(application_id, base, bonus, equity, currency, location, received_at, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (application_id, base, bonus, equity, currency, location, received_at, notes),
        )
    return int(cur.lastrowid or 0)


def get(conn: sqlite3.Connection, offer_id: int) -> dict[str, Any] | None:
    """Fetch a single offer by id."""
    row = conn.execute("SELECT * FROM offer WHERE id = ?", (offer_id,)).fetchone()
    return serialize(row) if row else None


def list_for_app(conn: sqlite3.Connection, application_id: int) -> list[dict[str, Any]]:
    """All offers for one application, newest first."""
    rows = conn.execute(
        "SELECT * FROM offer WHERE application_id = ? ORDER BY id DESC",
        (application_id,),
    ).fetchall()
    return [serialize(r) for r in rows]


def list_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """All offers across all applications, newest first."""
    rows = conn.execute("SELECT * FROM offer ORDER BY id DESC").fetchall()
    return [serialize(r) for r in rows]


def set_status(conn: sqlite3.Connection, offer_id: int, status: str) -> dict[str, Any] | None:
    """Transition an offer to a new status. Returns the updated offer, or None if not found."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; must be one of {VALID_STATUSES}")
    with transaction(conn):
        conn.execute(
            "UPDATE offer SET status = ? WHERE id = ?",
            (status, offer_id),
        )
    return get(conn, offer_id)


def update(conn: sqlite3.Connection, offer_id: int, **fields: Any) -> dict[str, Any] | None:
    """Patch arbitrary mutable columns. Unknown field names raise ValueError."""
    if not fields:
        return get(conn, offer_id)
    unknown = set(fields) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown offer field(s): {unknown}")
    set_clause = ", ".join(f"{col} = ?" for col in fields)
    params: list[Any] = list(fields.values())
    params.append(offer_id)
    with transaction(conn):
        conn.execute(
            f"UPDATE offer SET {set_clause} WHERE id = ?",  # noqa: S608 — set_clause built from allowlist
            params,
        )
    return get(conn, offer_id)
