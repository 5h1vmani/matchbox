"""Tier-1: source-reported salary/employment flow from JobRecord into the job row,
alongside the Tier-2 enrichment that runs on every ingested job."""

from __future__ import annotations

from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.discovery.aggregators import _adzuna_employment
from matchbox.discovery.base import JobRecord
from matchbox.discovery.runner import _upsert_jobs


def test_salary_persists_through_upsert(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    rec = JobRecord(
        ats_type="greenhouse",
        source_slug="adzuna:in",
        company="Acme",
        title="Senior Engineer",
        location="Pune",
        url="https://j/1",
        apply_url="https://j/1",
        jd_text="Build things.",
        posted_at=None,
        country="in",
        remote=False,
        salary_min=2_000_000.0,
        salary_max=3_000_000.0,
        salary_currency="INR",
        salary_period="year",
        employment_type="full_time",
    )
    assert _upsert_jobs(conn, None, [rec]) == 1
    row = conn.execute(
        "SELECT salary_min, salary_max, salary_currency, employment_type, seniority "
        "FROM job WHERE url = 'https://j/1'"
    ).fetchone()
    assert row["salary_min"] == 2_000_000.0
    assert row["salary_max"] == 3_000_000.0
    assert row["salary_currency"] == "INR"
    assert row["employment_type"] == "full_time"
    assert row["seniority"] == "senior"  # Tier-2 still runs alongside Tier-1
    conn.close()


def test_ats_records_leave_salary_null(tmp_path: Path) -> None:
    """An ATS poller record (no salary) inserts cleanly with NULL salary."""
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    rec = JobRecord(
        ats_type="greenhouse",
        source_slug="acme",
        company="Acme",
        title="Engineer",
        location="Remote",
        url="https://j/2",
        apply_url=None,
        jd_text="jd",
        posted_at=None,
    )
    assert _upsert_jobs(conn, None, [rec]) == 1
    row = conn.execute(
        "SELECT salary_min, employment_type FROM job WHERE url='https://j/2'"
    ).fetchone()
    assert row["salary_min"] is None
    assert row["employment_type"] is None
    conn.close()


def test_adzuna_employment_mapping() -> None:
    assert _adzuna_employment({"contract_time": "full_time"}) == "full_time"
    assert _adzuna_employment({"contract_time": "part_time"}) == "part_time"
    assert _adzuna_employment({"contract_type": "contract"}) == "contract"
    assert _adzuna_employment({"contract_type": "permanent"}) == "full_time"
    assert _adzuna_employment({}) is None
