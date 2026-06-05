"""The v0.3 -> v0.4 backfill: bullets/projects -> claims + default renderings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import SCHEMA_FILE, migrate
from matchbox.graph.backfill import backfill_graph


def _v1_db(path: Path) -> sqlite3.Connection:
    """A DB at version 1 (v0.3 schema), ready to be migrated to v0.4."""
    conn = connect(path)
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO migration (version) VALUES (1)")
    return conn


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO experience (id, company, role) VALUES (1, 'Acme', 'Engineer')")
    conn.execute(
        "INSERT INTO bullet (experience_id, text, facts_verified) VALUES (1, 'Shipped X', 1)"
    )
    conn.execute("INSERT INTO bullet (experience_id, text, facts_verified) VALUES (1, 'Did Y', 0)")
    conn.execute("INSERT INTO project (name, text, facts_verified) VALUES ('P', 'Built P', 1)")


def test_backfill_maps_bullets_and_projects(tmp_path: Path) -> None:
    conn = _v1_db(tmp_path / "m.db")
    _seed(conn)
    migrate(conn)

    # 2 bullets + 1 project -> 3 claims, 3 default renderings, none lost.
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0] == 3

    verification = {
        r["assertion"]: r["verification"]
        for r in conn.execute("SELECT assertion, verification FROM claim")
    }
    assert verification["Shipped X"] == "self_attested"
    assert verification["Did Y"] == "unverified"
    assert verification["Built P"] == "self_attested"

    kind = {r["assertion"]: r["kind"] for r in conn.execute("SELECT assertion, kind FROM claim")}
    assert kind["Shipped X"] == "accomplishment"
    assert kind["Built P"] == "credential"

    rendering = conn.execute(
        "SELECT r.text, r.approved, r.job_id "
        "FROM rendering r JOIN claim c ON r.claim_id = c.id "
        "WHERE c.assertion = 'Shipped X'"
    ).fetchone()
    assert rendering["text"] == "Shipped X"
    assert rendering["approved"] == 1
    assert rendering["job_id"] is None
    conn.close()


def test_verified_state_maps_to_verified_at(tmp_path: Path) -> None:
    conn = _v1_db(tmp_path / "m.db")
    _seed(conn)
    migrate(conn)
    verified_at = {
        r["assertion"]: r["verified_at"]
        for r in conn.execute("SELECT assertion, verified_at FROM claim")
    }
    assert verified_at["Shipped X"] is not None
    assert verified_at["Did Y"] is None
    conn.close()


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    conn = _v1_db(tmp_path / "m.db")
    _seed(conn)
    migrate(conn)
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 3

    backfill_graph(conn)  # an explicit second run must not duplicate
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0] == 3
    conn.close()


def test_empty_db_backfills_to_nothing(tmp_path: Path) -> None:
    conn = _v1_db(tmp_path / "m.db")
    migrate(conn)  # no bullets/projects seeded
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0] == 0
    conn.close()
