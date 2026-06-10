"""Scan-time country inference + persisted India eligibility (runner)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.discovery.base import JobRecord
from matchbox.discovery.runner import _upsert_jobs, backfill_enrichment


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "matchbox.db")
    migrate(c)
    return c


def _record(**kw: object) -> JobRecord:
    base: dict = {
        "ats_type": "greenhouse",
        "source_slug": "acme",
        "company": "Acme",
        "title": "Engineer",
        "location": None,
        "url": "https://acme.test/1",
        "apply_url": None,
        "jd_text": "Build services.",
        "posted_at": None,
    }
    base.update(kw)
    return JobRecord(**base)


def _job(conn: sqlite3.Connection, url: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM job WHERE url = ?", (url,)).fetchone()


def test_india_location_sets_country_and_eligibility(conn: sqlite3.Connection) -> None:
    _upsert_jobs(conn, None, [_record(location="Bengaluru, India", url="https://a/1")])
    row = _job(conn, "https://a/1")
    assert row["country"] == "in"
    assert json.loads(row["eligibility_json"]) == {"india": True}


def test_foreign_location_leaves_country_null_and_ineligible(conn: sqlite3.Connection) -> None:
    _upsert_jobs(conn, None, [_record(location="New York, NY", url="https://a/2")])
    row = _job(conn, "https://a/2")
    assert row["country"] is None
    assert json.loads(row["eligibility_json"]) == {"india": False}


def test_source_country_wins_over_inference(conn: sqlite3.Connection) -> None:
    _upsert_jobs(conn, None, [_record(location="Bengaluru", country="us", url="https://a/3")])
    row = _job(conn, "https://a/3")
    assert row["country"] == "us"


def test_indianapolis_does_not_false_match(conn: sqlite3.Connection) -> None:
    _upsert_jobs(conn, None, [_record(location="Indianapolis, IN", url="https://a/4")])
    row = _job(conn, "https://a/4")
    assert row["country"] is None
    assert json.loads(row["eligibility_json"]) == {"india": False}


def test_backfill_fills_country_and_eligibility(conn: sqlite3.Connection) -> None:
    # Simulate a pre-fix row: inserted without country/eligibility.
    conn.execute(
        "INSERT INTO job (company, title, url, jd_text, location, status) "
        "VALUES ('TCS', 'Consultant', 'https://a/5', 'JD', 'Hyderabad, India', 'scored')"
    )
    n = backfill_enrichment(conn)
    assert n >= 1
    row = _job(conn, "https://a/5")
    assert row["country"] == "in"
    assert json.loads(row["eligibility_json"]) == {"india": True}
    # Idempotent: a second run touches nothing.
    assert backfill_enrichment(conn) == 0
