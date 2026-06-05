"""Summarise a profile's evidence graph.

    python -m matchbox.graph.summary [--db PATH]

Migrates the target DB (exactly as the app does on every request), then
prints counts so a human can confirm the v0.3 -> v0.4 backfill preserved
everything. Prints counts only, no claim text, so it is safe to run on a
real profile.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import applied_versions, migrate

_TIERS = ("unverified", "self_attested", "artifact_backed", "reference_backed")


def _count(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def summarize(conn: sqlite3.Connection) -> str:
    experiences = _count(conn, "SELECT COUNT(*) FROM experience")
    bullets = _count(conn, "SELECT COUNT(*) FROM bullet")
    projects = _count(conn, "SELECT COUNT(*) FROM project")
    claims = _count(conn, "SELECT COUNT(*) FROM claim")
    renderings = _count(conn, "SELECT COUNT(*) FROM rendering")
    accomplishments = _count(conn, "SELECT COUNT(*) FROM claim WHERE kind = 'accomplishment'")
    credentials = _count(conn, "SELECT COUNT(*) FROM claim WHERE kind = 'credential'")
    version = max(applied_versions(conn))
    tiers = {
        t: _count(conn, "SELECT COUNT(*) FROM claim WHERE verification = ?", (t,)) for t in _TIERS
    }

    expected = bullets + projects
    ok = "OK" if claims == expected and renderings == expected else "MISMATCH"

    lines = [
        f"schema version: {version}",
        "",
        "v0.3 library            v0.4 graph",
        f"  experiences {experiences:>5}",
        f"  bullets     {bullets:>5}  ->  accomplishment claims {accomplishments:>5}",
        f"  projects    {projects:>5}  ->  credential claims     {credentials:>5}",
        f"                            renderings            {renderings:>5}",
        "",
        "trust gradient:",
        *[f"  {t:<18}{tiers[t]:>5}" for t in _TIERS],
        "",
        f"backfill check: bullets+projects={expected} vs claims={claims}, "
        f"renderings={renderings}  ->  {ok}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise the evidence graph.")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to a matchbox.db (default: active profile)",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    try:
        migrate(conn)
        print(summarize(conn))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
