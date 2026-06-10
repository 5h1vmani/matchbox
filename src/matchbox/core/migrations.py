"""Schema migrations.

Version 1 is the full baseline in ``schema.sql``. Later versions are
``NNN_*.sql`` files (DDL or data SQL) discovered alongside this module,
plus optional Python data-migration steps registered in ``_PY_STEPS`` that
run after the SQL of the same version. Each version is applied exactly
once and recorded in the ``migration`` table.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from matchbox.core.db import connect
from matchbox.graph.backfill import backfill_graph

_DIR = Path(__file__).parent
SCHEMA_FILE = _DIR / "schema.sql"  # version 1 baseline


def _add_eligibility_column(conn: sqlite3.Connection) -> None:
    """011: job.eligibility_json — persisted deterministic geo eligibility.

    Conditional on purpose: long-lived DBs already carry this column from a
    pre-migration era, and SQLite has no ADD COLUMN IF NOT EXISTS, so a plain
    SQL migration would fail exactly where the column already exists."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(job)")}
    if "eligibility_json" not in cols:
        conn.execute("ALTER TABLE job ADD COLUMN eligibility_json TEXT")


# Python data steps that run AFTER the SQL of the same version, keyed by
# version number. DDL belongs in the matching NNN_*.sql file; these are for
# row-by-row data transformations the SQL layer cannot express cleanly (or,
# like 011, DDL that must be conditional).
_PY_STEPS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: backfill_graph,
    11: _add_eligibility_column,
}


def _sql_migrations() -> dict[int, Path]:
    """Discover ``NNN_*.sql`` migration files (002 and up)."""
    found: dict[int, Path] = {}
    for path in _DIR.glob("[0-9][0-9][0-9]_*.sql"):
        found[int(path.name[:3])] = path
    return found


def target_version() -> int:
    """Highest version this build knows how to produce."""
    return max({1, *_sql_migrations(), *_PY_STEPS})


CURRENT_VERSION = target_version()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration versions already recorded.

    If the ``migration`` table does not exist yet, return an empty set.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='migration'"
    ).fetchone()
    if row is None:
        return set()
    return {int(r[0]) for r in conn.execute("SELECT version FROM migration")}


def _apply(conn: sqlite3.Connection, version: int) -> None:
    """Apply a single version: its SQL, then any Python step, then record it."""
    if version == 1:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    else:
        sql_file = _sql_migrations().get(version)
        if sql_file is not None:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
    step = _PY_STEPS.get(version)
    if step is not None:
        step(conn)
    conn.execute("INSERT INTO migration (version) VALUES (?)", (version,))


def migrate(conn: sqlite3.Connection | None = None) -> int:
    """Bring the DB up to ``target_version()``. Returns that version.

    Applies every version not yet recorded, in order. Safe to call on a
    fresh DB or one already at the latest version (a no-op then).
    """
    owned = conn is None
    if conn is None:
        conn = connect()
    try:
        applied = applied_versions(conn)
        for version in range(1, target_version() + 1):
            if version not in applied:
                _apply(conn, version)
        return target_version()
    finally:
        if owned:
            conn.close()
