"""Answer-library DAL: serialize + CRUD over the `answer` table (migration 008).

The only place SQL touches `answer`. Mirrors the library DAL conventions: writes
go through autocommit (the connection runs `isolation_level=None`) rather than an
explicit transaction, so these compose inside `ingest`'s outer transaction
without nesting BEGINs. The `facts_verified` gate works exactly like `bullet`'s,
and `used_count` is bumped when an answer is selected for an application.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    """One answer row -> camelCase dict for the SPA / CLI."""
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "category": row["category"],
        "verified": bool(row["facts_verified"]),
        "usedCount": row["used_count"],
        "sourceFile": row["source_file"],
        "createdAt": row["created_at"],
    }


def create(
    conn: sqlite3.Connection,
    *,
    question: str,
    answer: str,
    category: str | None = None,
    facts_verified: bool = False,
    source_file: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO answer (question, answer, category, facts_verified, source_file) "
        "VALUES (?, ?, ?, ?, ?)",
        (question, answer, category, int(facts_verified), source_file),
    )
    return int(cur.lastrowid or 0)


def get(conn: sqlite3.Connection, answer_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM answer WHERE id = ?", (answer_id,)).fetchone()
    return serialize(row) if row else None


def list_all(
    conn: sqlite3.Connection, *, verified: bool | None = None
) -> list[dict[str, Any]]:
    """All answers, newest first. `verified` filters by the gate when set."""
    sql = "SELECT * FROM answer"
    params: list[Any] = []
    if verified is not None:
        sql += " WHERE facts_verified = ?"
        params.append(int(verified))
    sql += " ORDER BY id DESC"
    return [serialize(r) for r in conn.execute(sql, params).fetchall()]


def update(
    conn: sqlite3.Connection,
    answer_id: int,
    *,
    question: str | None = None,
    answer: str | None = None,
    category: str | None = None,
    facts_verified: bool | None = None,
) -> dict[str, Any] | None:
    """Partial update (the inline editor / the /review verify toggle)."""
    fields: list[str] = []
    values: list[Any] = []
    if question is not None:
        fields.append("question = ?")
        values.append(question)
    if answer is not None:
        fields.append("answer = ?")
        values.append(answer)
    if category is not None:
        fields.append("category = ?")
        values.append(category)
    if facts_verified is not None:
        fields.append("facts_verified = ?")
        values.append(int(facts_verified))
    if fields:
        values.append(answer_id)
        conn.execute(f"UPDATE answer SET {', '.join(fields)} WHERE id = ?", values)
    return get(conn, answer_id)


def mark_used(conn: sqlite3.Connection, answer_id: int) -> dict[str, Any] | None:
    """Increment `used_count` when an answer is selected for an application."""
    conn.execute("UPDATE answer SET used_count = used_count + 1 WHERE id = ?", (answer_id,))
    return get(conn, answer_id)


def delete(conn: sqlite3.Connection, answer_id: int) -> None:
    conn.execute("DELETE FROM answer WHERE id = ?", (answer_id,))
