"""Tests for run creation — the work-queue.json writer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from matchbox.core.db import PROJECT_ROOT
from matchbox.scoring.runs import JobSelection, _allocate_run_id, create_run


@pytest.fixture()
def db_with_jobs(tmp_db: sqlite3.Connection) -> sqlite3.Connection:
    tmp_db.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, status) VALUES (?, ?, ?, ?, ?, 'scored')",
        ("Anthropic", "FDE", "https://x/1", "JD text 1", "https://apply/1"),
    )
    tmp_db.execute(
        "INSERT INTO job (company, title, url, jd_text, status) VALUES (?, ?, ?, ?, 'scored')",
        ("Modal", "MLE", "https://x/2", "JD text 2"),
    )
    return tmp_db


def test_allocate_run_id_monotonic(tmp_db: sqlite3.Connection) -> None:
    today = "2026-05-22"
    rid1 = _allocate_run_id(tmp_db, today=today)
    assert rid1 == "2026-05-22-001"
    tmp_db.execute("INSERT INTO run (id, status) VALUES (?, 'queued')", (rid1,))
    rid2 = _allocate_run_id(tmp_db, today=today)
    assert rid2 == "2026-05-22-002"


def test_create_run_writes_valid_work_queue(
    db_with_jobs: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Re-point RUNS_DIR + SCHEMA path resolution at tmp_path for test isolation.
    from matchbox.scoring import runs as runs_mod

    monkeypatch.setattr(runs_mod, "RUNS_DIR", tmp_path / "runs")

    run_id, queue_path = create_run(
        db_with_jobs,
        selections=[
            JobSelection(job_id=1, want_cv=True, want_cover=True),
            JobSelection(job_id=2, want_cv=True, want_cover=False),
        ],
        palette="slate",
        font="source-serif",
        today="2026-05-22",
    )
    assert run_id == "2026-05-22-001"
    assert queue_path.exists()

    payload = json.loads(queue_path.read_text())
    schema = json.loads((PROJECT_ROOT / "schemas" / "work-queue.v1.json").read_text())
    Draft202012Validator(schema).validate(payload)

    assert payload["schema_version"] == 1
    assert payload["run_id"] == run_id
    assert len(payload["jobs"]) == 2
    assert payload["jobs"][0]["job_id"] == 1
    assert payload["jobs"][0]["want_cv"] is True
    assert payload["jobs"][0]["want_cover"] is True
    assert payload["jobs"][0]["palette"] == "slate"

    # Side effects in DB
    rows = db_with_jobs.execute("SELECT id, status FROM job WHERE id IN (1, 2)").fetchall()
    assert all(r["status"] == "selected" for r in rows)

    rj = db_with_jobs.execute(
        "SELECT run_id, job_id, want_cv, want_cover FROM run_job WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    assert len(rj) == 2


def test_create_run_rejects_unknown_job(
    db_with_jobs: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matchbox.scoring import runs as runs_mod

    monkeypatch.setattr(runs_mod, "RUNS_DIR", tmp_path / "runs")
    with pytest.raises(LookupError):
        create_run(
            db_with_jobs,
            selections=[JobSelection(job_id=9999, want_cv=True, want_cover=False)],
            today="2026-05-22",
        )


def test_create_run_validates_palette_via_schema(
    db_with_jobs: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matchbox.scoring import runs as runs_mod

    monkeypatch.setattr(runs_mod, "RUNS_DIR", tmp_path / "runs")
    with pytest.raises(ValueError) as exc:
        create_run(
            db_with_jobs,
            selections=[JobSelection(job_id=1, want_cv=True, want_cover=False)],
            palette="rainbow",  # not in the schema enum
            today="2026-05-22",
        )
    assert "schema validation" in str(exc.value)
