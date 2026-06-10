"""Tests for the jobfacts CLI (brain Tier-2 precise enrichment)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.jobfacts import main, save_facts


@pytest.fixture()
def db_with_job(tmp_path: Path) -> tuple[Path, int, sqlite3.Connection]:
    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status, seniority) "
        "VALUES (?, ?, ?, ?, 'scored', 'senior')",
        ("Deloitte", "Finance AI Engineer", "https://x/1", "JD text"),
    )
    assert cur.lastrowid is not None
    return db, cur.lastrowid, conn


def _payload(job_id: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": job_id,
        "salary_min": 3500000,
        "salary_max": 5000000,
        "salary_currency": "INR",
        "salary_period": "year",
        "employment_type": "full_time",
        "min_years_exp": 5,
        "role_family": "ai-transformation",
        "country": "in",
    }


def test_save_facts_writes_supplied_columns(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    written = save_facts(conn, job_id, _payload(job_id))
    assert "salary_min" in written and "country" in written
    row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    assert row["salary_min"] == 3500000
    assert row["salary_currency"] == "INR"
    assert row["employment_type"] == "full_time"
    assert row["role_family"] == "ai-transformation"
    assert row["country"] == "in"


def test_save_facts_is_partial_omitted_fields_untouched(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    # Payload omits seniority; the scan-time value must survive.
    save_facts(conn, job_id, {"schema_version": 1, "job_id": job_id, "country": "in"})
    row = conn.execute("SELECT seniority, country FROM job WHERE id = ?", (job_id,)).fetchone()
    assert row["seniority"] == "senior"
    assert row["country"] == "in"


def test_save_facts_explicit_null_clears(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    save_facts(conn, job_id, {"schema_version": 1, "job_id": job_id, "seniority": None})
    row = conn.execute("SELECT seniority FROM job WHERE id = ?", (job_id,)).fetchone()
    assert row["seniority"] is None


def test_save_facts_rejects_job_id_mismatch(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    with pytest.raises(ValueError, match="job_id mismatch"):
        save_facts(conn, job_id, _payload(job_id + 1))


def test_save_facts_rejects_bad_enum(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    bad = {"schema_version": 1, "job_id": job_id, "employment_type": "permanent"}
    with pytest.raises(ValueError, match="schema validation"):
        save_facts(conn, job_id, bad)


def test_save_facts_rejects_empty_payload(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    with pytest.raises(ValueError, match="no fact fields"):
        save_facts(conn, job_id, {"schema_version": 1, "job_id": job_id})


def test_cli_exit_codes(db_with_job: tuple[Path, int, sqlite3.Connection], tmp_path: Path) -> None:
    db, job_id, conn = db_with_job
    conn.close()

    good = tmp_path / "facts.json"
    good.write_text(json.dumps(_payload(job_id)))
    assert main(["save", "--job", str(job_id), "--file", str(good), "--db", str(db)]) == 0

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1, "job_id": job_id, "country": "India"}))
    assert main(["save", "--job", str(job_id), "--file", str(bad), "--db", str(db)]) == 3

    assert main(["save", "--job", "99999", "--file", str(good), "--db", str(db)]) == 3  # mismatch
    retargeted = tmp_path / "retargeted.json"
    retargeted.write_text(json.dumps({"schema_version": 1, "job_id": 99999, "country": "in"}))
    assert main(["save", "--job", "99999", "--file", str(retargeted), "--db", str(db)]) == 4
