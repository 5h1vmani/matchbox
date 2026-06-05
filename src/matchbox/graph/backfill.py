"""One-time backfill of the v0.3 library into the v0.4 evidence graph.

Runs as the Python step for migration version 2 (see ``migrations.py``).
Each ``bullet`` becomes an ``accomplishment`` claim; each ``project`` a
``credential`` claim. Every claim gets one default ``rendering`` carrying
the original text verbatim, marked ``approved`` (grandfathered as already
truthful). The ``facts_verified`` boolean maps onto the trust gradient:
verified -> ``self_attested``, otherwise ``unverified``.

Idempotent: does nothing once the ``claim`` table is non-empty, and the
inserts run inside one transaction so a partial failure rolls back cleanly
and the next ``migrate()`` retries from scratch.
"""

from __future__ import annotations

import sqlite3

from matchbox.core.db import transaction


def backfill_graph(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0]:
        return  # already backfilled

    with transaction(conn):
        for b in conn.execute(
            "SELECT experience_id, text, facts_verified, source_file, created_at "
            "FROM bullet ORDER BY id"
        ).fetchall():
            verified = bool(b["facts_verified"])
            cur = conn.execute(
                "INSERT INTO claim "
                "(experience_id, kind, assertion, verification, source_file, "
                " created_at, verified_at) "
                "VALUES (?, 'accomplishment', ?, ?, ?, ?, ?)",
                (
                    b["experience_id"],
                    b["text"],
                    "self_attested" if verified else "unverified",
                    b["source_file"],
                    b["created_at"],
                    b["created_at"] if verified else None,
                ),
            )
            conn.execute(
                "INSERT INTO rendering (claim_id, job_id, text, approved, created_at) "
                "VALUES (?, NULL, ?, 1, ?)",
                (cur.lastrowid, b["text"], b["created_at"]),
            )

        for p in conn.execute("SELECT text, facts_verified FROM project ORDER BY id").fetchall():
            verified = bool(p["facts_verified"])
            cur = conn.execute(
                "INSERT INTO claim (experience_id, kind, assertion, verification) "
                "VALUES (NULL, 'credential', ?, ?)",
                (p["text"], "self_attested" if verified else "unverified"),
            )
            conn.execute(
                "INSERT INTO rendering (claim_id, job_id, text, approved) VALUES (?, NULL, ?, 1)",
                (cur.lastrowid, p["text"]),
            )
