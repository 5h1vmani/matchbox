"""Tests for the jobreqs CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.jobreqs import main, save_requirements


@pytest.fixture()
def db_with_job(tmp_path: Path) -> tuple[Path, int, sqlite3.Connection]:
    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status) VALUES (?, ?, ?, ?, 'scored')",
        ("Modal", "FDE", "https://x/1", "JD"),
    )
    assert cur.lastrowid is not None
    return db, cur.lastrowid, conn


def _payload(job_id: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": job_id,
        "model_version": "test-model-v1",
        "jd_hash": "abc123",
        "requirements": [
            {
                "type": "must-have",
                "text": "Operate Kubernetes clusters",
                "keywords": ["kubernetes"],
                "variants": ["k8s"],
            },
            {
                "type": "responsibility",
                "text": "Mentor engineers",
                "keywords": ["mentor"],
            },
        ],
    }


def test_save_requirements_writes_json(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    save_requirements(conn, job_id, _payload(job_id))
    row = conn.execute(
        "SELECT requirements_json, requirements_model, requirements_jd_hash FROM job WHERE id = ?",
        (job_id,),
    ).fetchone()
    assert row["requirements_model"] == "test-model-v1"
    assert row["requirements_jd_hash"] == "abc123"
    saved = json.loads(row["requirements_json"])
    assert len(saved["requirements"]) == 2


def test_save_requirements_rejects_bad_schema(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, job_id, conn = db_with_job
    bad = {
        "schema_version": 1,
        "job_id": job_id,
        "model_version": "x",
        "requirements": [{"type": "nope", "text": "x"}],  # invalid enum
    }
    with pytest.raises(ValueError) as exc:
        save_requirements(conn, job_id, bad)
    assert "schema validation" in str(exc.value)


def test_save_requirements_unknown_job(
    db_with_job: tuple[Path, int, sqlite3.Connection],
) -> None:
    _, _, conn = db_with_job
    with pytest.raises(LookupError):
        save_requirements(conn, 99999, _payload(99999))


def test_main_writes(db_with_job: tuple[Path, int, sqlite3.Connection], tmp_path: Path) -> None:
    db, job_id, _ = db_with_job
    path = tmp_path / "reqs.json"
    path.write_text(json.dumps(_payload(job_id)))
    rc = main(["save", "--job", str(job_id), "--file", str(path), "--db", str(db)])
    assert rc == 0


def test_main_bad_schema_returns_3(
    db_with_job: tuple[Path, int, sqlite3.Connection],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db, job_id, _ = db_with_job
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1, "job_id": job_id}))
    rc = main(["save", "--job", str(job_id), "--file", str(bad), "--db", str(db)])
    assert rc == 3
    assert "schema" in capsys.readouterr().err.lower()


def test_main_unknown_job_returns_4(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "matchbox.db"
    payload_path = tmp_path / "reqs.json"
    payload_path.write_text(json.dumps(_payload(9999)))
    rc = main(["save", "--job", "9999", "--file", str(payload_path), "--db", str(db)])
    assert rc == 4
