"""The migration runner: discovery, ordering, idempotency, upgrade-in-place."""

from __future__ import annotations

from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import (
    CURRENT_VERSION,
    SCHEMA_FILE,
    applied_versions,
    migrate,
    target_version,
)


def test_target_version_is_at_least_two() -> None:
    assert target_version() >= 2
    assert target_version() == CURRENT_VERSION


def test_fresh_db_applies_every_version(tmp_path: Path) -> None:
    conn = connect(tmp_path / "m.db")
    assert migrate(conn) == target_version()
    assert applied_versions(conn) == set(range(1, target_version() + 1))
    for table in ("claim", "evidence", "rendering"):
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")  # raises if table missing
    # 007 SOTA foundation: new tables present, new columns selectable.
    for table in ("company", "requirement", "artifact", "offer", "agent_task", "voice_profile"):
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")  # raises if table missing
    conn.execute("SELECT salary_min, seniority, dedup_key, company_id FROM job LIMIT 1")
    conn.execute("SELECT predicted_band, predicted_score FROM application LIMIT 1")
    conn.execute("SELECT work_auth_json FROM target LIMIT 1")
    conn.close()


def test_007_backfills_company_and_dedup_key(tmp_path: Path) -> None:
    """A job present before 007 gets a company row + a dedup key after migrate."""
    conn = connect(tmp_path / "m.db")
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO migration (version) VALUES (1)")
    conn.execute(
        "INSERT INTO job (company, title, location, url, jd_text) "
        "VALUES ('Modal', 'FDE', 'Remote', 'https://j/1', 'jd')"
    )
    migrate(conn)
    row = conn.execute("SELECT company_id, dedup_key FROM job WHERE company = 'Modal'").fetchone()
    assert row[0] is not None, "company_id backfilled"
    assert row[1] == "https://j/1", "dedup_key = canonical url"
    name = conn.execute("SELECT name FROM company WHERE id = ?", (row[0],)).fetchone()[0]
    assert name == "Modal"
    conn.close()


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "m.db")
    assert migrate(conn) == target_version()
    before = applied_versions(conn)
    assert migrate(conn) == target_version()
    assert applied_versions(conn) == before
    conn.close()


def test_upgrades_a_v1_only_db(tmp_path: Path) -> None:
    """A DB left at v0.3 (version 1 only) gets the graph applied in place."""
    conn = connect(tmp_path / "m.db")
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO migration (version) VALUES (1)")
    assert applied_versions(conn) == {1}

    migrate(conn)
    assert applied_versions(conn) == set(range(1, target_version() + 1))
    conn.execute("SELECT 1 FROM claim LIMIT 1")  # raises if table missing
    conn.close()
