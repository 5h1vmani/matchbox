"""Tests for the onboarding ingest CLI — the brain's write path."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from matchbox.core import library as lib
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.onboarding.ingest_cli import ingest, main


@pytest.fixture()
def empty_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    return conn


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "experiences": [
            {
                "company": "Modal",
                "role": "Forward Deployed Engineer",
                "start_date": "2024-01",
                "end_date": None,
                "bullets": [
                    {
                        "text": "Built ETL pipelines processing 30M rows/day.",
                        "has_metric": True,
                        "source_file": "old-cv.pdf",
                        "tags": [
                            {"facet": "tech", "value": "python"},
                            {"facet": "impact", "value": "metric"},
                        ],
                    },
                    {
                        "text": "Shipped streaming inference.",
                        "tags": [{"facet": "tech", "value": "streaming"}],
                    },
                ],
            },
        ],
        "projects": [
            {
                "name": "Matchbox",
                "text": "Local CV tailoring tool.",
                "tags": [{"facet": "tech", "value": "python"}],
            }
        ],
        "skills": [
            {"name": "Python", "category": "languages", "proficiency": "expert"},
            {"name": "Rust", "category": "languages"},
        ],
        "summaries": [{"label": "ml-focus", "text": "ML-leaning generalist engineer."}],
    }
    base.update(overrides)
    return base


def test_ingest_populates_unverified_rows(empty_db: sqlite3.Connection) -> None:
    counts = ingest(_payload(), empty_db)

    assert counts == {
        "experiences": 1,
        "bullets": 2,
        "projects": 1,
        "skills": 2,
        "summaries": 1,
        "answers": 0,
        "tags": 4,
    }

    [exp] = lib.list_experiences(empty_db)
    bullets = lib.list_bullets(empty_db, experience_id=exp.id)
    assert len(bullets) == 2
    for b in bullets:
        assert b.facts_verified is False  # land unverified

    [p] = lib.list_projects(empty_db)
    assert p.facts_verified is False


def test_ingest_attaches_tags(empty_db: sqlite3.Connection) -> None:
    ingest(_payload(), empty_db)
    [exp] = lib.list_experiences(empty_db)
    bullets = lib.bullets_with_tags(empty_db, experience_id=exp.id)
    first = bullets[0]
    assert {(t.facet, t.value) for t in first.tags} == {
        ("tech", "python"),
        ("impact", "metric"),
    }


def test_ingest_dedupes_existing_skill(empty_db: sqlite3.Connection) -> None:
    lib.add_skill(empty_db, name="Python", proficiency="working")
    counts = ingest(_payload(), empty_db)
    # Pre-existing Python was not re-counted (the CLI silently de-dupes).
    assert counts["skills"] == 1  # only Rust


def test_main_validates_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1, "experiences": [{"company": "X"}]}))
    db = tmp_path / "matchbox.db"
    rc = main(["--file", str(bad), "--db", str(db)])
    out = capsys.readouterr()
    assert rc == 3, out
    assert "schema error" in out.err


def test_main_writes_rows(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload()))
    db = tmp_path / "matchbox.db"
    rc = main(["--file", str(payload_path), "--db", str(db)])
    assert rc == 0

    conn = connect(db)
    try:
        assert len(lib.list_experiences(conn)) == 1
        assert len(lib.list_projects(conn)) == 1
        assert len(lib.list_skills(conn)) == 2
    finally:
        conn.close()


def test_main_rejects_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    rc = main(["--file", str(bad), "--db", str(tmp_path / "x.db")])
    assert rc == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_ingest_persists_profile(empty_db: sqlite3.Connection) -> None:
    payload = _payload(
        profile={
            "full_name": "Shiva Padakanti",
            "email": "shiva@example.com",
            "links": ["https://github.com/shiva"],
            "headline": "Generalist engineer",
        }
    )
    ingest(payload, empty_db)
    row = empty_db.execute("SELECT * FROM profile").fetchone()
    assert row["full_name"] == "Shiva Padakanti"
    assert json.loads(row["links_json"]) == ["https://github.com/shiva"]
