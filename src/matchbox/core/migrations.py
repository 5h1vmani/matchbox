"""Schema migrations — minimal.

v1 applies the full `schema.sql`. Future versions add additional files named
`002_*.sql`, `003_*.sql`, ... — each runs once and is recorded in the
`migration` table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from matchbox.core.db import connect

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
CURRENT_VERSION = 1


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration versions already recorded.

    If the `migration` table does not exist yet, return an empty set.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='migration'"
    ).fetchone()
    if row is None:
        return set()
    return {r[0] for r in conn.execute("SELECT version FROM migration")}


def migrate(conn: sqlite3.Connection | None = None) -> int:
    """Bring the DB up to `CURRENT_VERSION`. Returns the version that ended up
    applied (which may equal the previous CURRENT_VERSION if nothing new).
    """
    owned = conn is None
    if conn is None:
        conn = connect()
    try:
        applied = applied_versions(conn)
        if 1 not in applied:
            sql = SCHEMA_FILE.read_text(encoding="utf-8")
            # executescript implicitly commits any pending transaction, so we
            # cannot wrap it in BEGIN/COMMIT — it is already atomic per script.
            conn.executescript(sql)
            conn.execute("INSERT INTO migration (version) VALUES (1)")
        return CURRENT_VERSION
    finally:
        if owned:
            conn.close()
