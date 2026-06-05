"""Runner-level aggregator scan: stores remote jobs with source=NULL + tags."""

from __future__ import annotations

import sqlite3

from matchbox.discovery import runner
from matchbox.discovery.aggregators import AggregatorError
from matchbox.discovery.base import JobRecord


def _rec(url: str, *, country: str | None, remote: bool) -> JobRecord:
    return JobRecord(
        ats_type="greenhouse",  # placeholder; aggregators store with source=NULL
        source_slug="agg",
        company="Acme",
        title="Engineer",
        location="Worldwide",
        url=url,
        apply_url=url,
        jd_text="Build things remotely.",
        posted_at=None,
        country=country,
        remote=remote,
    )


def test_scan_aggregators_stores_remote_jobs(tmp_db: sqlite3.Connection, monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "poll_himalayas",
        lambda *, client: [_rec("https://x/h1", country=None, remote=True)],
    )
    monkeypatch.setattr(
        runner, "poll_remotive", lambda *, client: [_rec("https://x/r1", country=None, remote=True)]
    )

    results = runner.scan_aggregators(tmp_db, himalayas=True, remotive=True)

    assert {r.name for r in results} == {"himalayas", "remotive"}
    assert all(r.ok and r.inserted == 1 for r in results)
    rows = tmp_db.execute("SELECT url, remote, source, status FROM job ORDER BY url").fetchall()
    assert [r["url"] for r in rows] == ["https://x/h1", "https://x/r1"]
    assert all(r["remote"] == 1 for r in rows)  # tagged remote
    assert all(r["source"] is None for r in rows)  # not an ats_source
    assert all(r["status"] == "new" for r in rows)


def test_scan_aggregators_adzuna_only_with_key(tmp_db: sqlite3.Connection, monkeypatch) -> None:
    called = {"adzuna": 0}

    def fake_adzuna(**kwargs: object) -> list[JobRecord]:
        called["adzuna"] += 1
        return [_rec("https://x/a1", country="in", remote=False)]

    monkeypatch.setattr(runner, "poll_adzuna", fake_adzuna)
    # no key -> adzuna skipped
    runner.scan_aggregators(
        tmp_db, himalayas=False, remotive=False, adzuna={"queries": [{"country": "in"}]}
    )
    assert called["adzuna"] == 0

    # with key -> adzuna runs and tags country
    runner.scan_aggregators(
        tmp_db,
        himalayas=False,
        remotive=False,
        adzuna={"app_id": "x", "app_key": "y", "queries": [{"country": "in", "what": "engineer"}]},
    )
    assert called["adzuna"] == 1
    row = tmp_db.execute("SELECT country, remote FROM job WHERE url = 'https://x/a1'").fetchone()
    assert row["country"] == "in"


def test_scan_aggregators_failure_is_isolated(tmp_db: sqlite3.Connection, monkeypatch) -> None:
    def boom(*, client: object) -> list[JobRecord]:
        raise AggregatorError("himalayas", "rate limited (429)")

    monkeypatch.setattr(runner, "poll_himalayas", boom)
    monkeypatch.setattr(
        runner, "poll_remotive", lambda *, client: [_rec("https://x/r1", country=None, remote=True)]
    )

    results = runner.scan_aggregators(tmp_db, himalayas=True, remotive=True)
    by_name = {r.name: r for r in results}
    assert by_name["himalayas"].ok is False
    assert "rate limited" in (by_name["himalayas"].error or "")
    assert by_name["remotive"].ok is True  # one failure does not poison the other
    assert tmp_db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
