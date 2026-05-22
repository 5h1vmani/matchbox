"""Tests for the discovery layer — pollers and runner.

These mock httpx with `httpx.MockTransport`, so no network is touched.
The fixture responses mirror each ATS's documented shape.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest

from matchbox.discovery import pollers
from matchbox.discovery.base import PollerError
from matchbox.discovery.runner import probe, scan_all, scan_source


def _mock_client(responses: dict[str, dict | list | str | None]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url in responses:
            payload = responses[url]
            if payload is None:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=payload)
        return httpx.Response(500, text=f"unexpected URL: {url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


# ─── per-poller parsing ───────────────────────────────────────────────


def test_greenhouse_parse() -> None:
    client = _mock_client(
        {
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs": {
                "jobs": [
                    {
                        "title": "Forward Deployed Engineer",
                        "absolute_url": "https://job.example/1",
                        "location": {"name": "Remote"},
                        "content": "<p>Build <b>great</b> things</p>",
                        "updated_at": "2026-05-01T00:00:00Z",
                    }
                ]
            }
        }
    )
    rows = pollers.poll_greenhouse("anthropic", "Anthropic", client)
    assert len(rows) == 1
    assert rows[0].title == "Forward Deployed Engineer"
    assert "Build great things" in rows[0].jd_text
    assert "<" not in rows[0].jd_text
    assert rows[0].url == "https://job.example/1"


def test_lever_parse() -> None:
    client = _mock_client(
        {
            "https://api.lever.co/v0/postings/modal-labs": [
                {
                    "text": "ML Engineer",
                    "hostedUrl": "https://lever.example/2",
                    "categories": {"location": "SF"},
                    "descriptionPlain": "Do ML.",
                    "createdAt": 1700000000000,
                }
            ]
        }
    )
    rows = pollers.poll_lever("modal-labs", "Modal", client)
    assert rows[0].title == "ML Engineer"
    assert rows[0].location == "SF"
    assert rows[0].jd_text == "Do ML."


def test_ashby_parse() -> None:
    client = _mock_client(
        {
            "https://api.ashbyhq.com/posting-api/job-board/foo": {
                "jobs": [
                    {
                        "title": "Eng",
                        "jobUrl": "https://ashby.example/3",
                        "locationName": "NYC",
                        "descriptionHtml": "<div>JD</div>",
                        "publishedAt": "2026-04-01",
                    }
                ]
            }
        }
    )
    rows = pollers.poll_ashby("foo", "Foo", client)
    assert rows[0].jd_text == "JD"
    assert rows[0].location == "NYC"


def test_workable_parse() -> None:
    client = _mock_client(
        {
            "https://apply.workable.com/api/v3/accounts/acme/jobs": {
                "results": [
                    {
                        "title": "Senior Eng",
                        "url": "https://workable.example/4",
                        "location": {"city": "Berlin", "country": "DE"},
                        "description": "<p>desc</p>",
                        "published_on": "2026-03-01",
                    }
                ]
            }
        }
    )
    rows = pollers.poll_workable("acme", "Acme", client)
    assert rows[0].title == "Senior Eng"
    assert rows[0].location == "Berlin, DE"


def test_smartrecruiters_parse() -> None:
    client = _mock_client(
        {
            "https://api.smartrecruiters.com/v1/companies/acme/postings": {
                "content": [
                    {
                        "name": "Engineer",
                        "ref": "https://sr.example/5",
                        "applyUrl": "https://sr.example/5/apply",
                        "location": {"city": "London", "country": "UK"},
                        "createdOn": "2026-02-01",
                    }
                ],
                "totalFound": 1,
            }
        }
    )
    rows = pollers.poll_smartrecruiters("acme", "Acme", client)
    assert rows[0].url == "https://sr.example/5"
    assert rows[0].apply_url == "https://sr.example/5/apply"


def test_recruitee_parse() -> None:
    client = _mock_client(
        {
            "https://acme.recruitee.com/api/offers/": {
                "offers": [
                    {
                        "title": "Engineer",
                        "careers_apply_url": "https://recruitee.example/6/apply",
                        "city": "Amsterdam",
                        "country": "NL",
                        "description": "Build cool stuff.",
                        "published_at": "2026-01-01",
                    }
                ]
            }
        }
    )
    rows = pollers.poll_recruitee("acme", "Acme", client)
    assert rows[0].location == "Amsterdam, NL"


# ─── error paths ──────────────────────────────────────────────────────


def test_poller_404_surfaces_as_poller_error() -> None:
    client = _mock_client({"https://boards-api.greenhouse.io/v1/boards/bogus/jobs": None})
    with pytest.raises(PollerError) as exc:
        pollers.poll_greenhouse("bogus", "Bogus", client)
    assert "404" in str(exc.value)


def test_poller_unexpected_shape() -> None:
    client = _mock_client({"https://boards-api.greenhouse.io/v1/boards/x/jobs": {"nope": []}})
    with pytest.raises(PollerError) as exc:
        pollers.poll_greenhouse("x", "X", client)
    assert "shape" in str(exc.value)


def test_dispatch_includes_all_six() -> None:
    assert set(pollers.POLLERS) == {
        "greenhouse",
        "lever",
        "ashby",
        "workable",
        "smartrecruiters",
        "recruitee",
    }


# ─── runner ───────────────────────────────────────────────────────────


@pytest.fixture()
def db_with_source(tmp_db: sqlite3.Connection) -> tuple[sqlite3.Connection, int]:
    cur = tmp_db.execute(
        "INSERT INTO ats_source (ats_type, slug, company) VALUES ('greenhouse', 'anthropic', 'Anthropic')"
    )
    assert cur.lastrowid is not None
    return tmp_db, cur.lastrowid


def test_scan_source_inserts_jobs_and_marks_ok(
    db_with_source: tuple[sqlite3.Connection, int],
) -> None:
    conn, src_id = db_with_source
    client = _mock_client(
        {
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs": {
                "jobs": [
                    {
                        "title": "Eng A",
                        "absolute_url": "https://job.example/a",
                        "location": {"name": "Remote"},
                        "content": "<p>JD A</p>",
                    },
                    {
                        "title": "Eng B",
                        "absolute_url": "https://job.example/b",
                        "location": {"name": "Remote"},
                        "content": "<p>JD B</p>",
                    },
                ]
            }
        }
    )
    src = dict(conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone())
    result = scan_source(conn, src, client=client, sleep=lambda *_: None)
    assert result.ok is True
    assert result.inserted == 2
    assert result.fetched == 2

    src_row = conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone()
    assert src_row["last_ok_at"] is not None
    assert src_row["last_error"] is None

    jobs = conn.execute("SELECT * FROM job WHERE source = ?", (src_id,)).fetchall()
    assert {j["url"] for j in jobs} == {
        "https://job.example/a",
        "https://job.example/b",
    }
    assert all(j["status"] == "new" for j in jobs)


def test_scan_source_dedupes_by_url(
    db_with_source: tuple[sqlite3.Connection, int],
) -> None:
    conn, src_id = db_with_source
    client = _mock_client(
        {
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs": {
                "jobs": [
                    {
                        "title": "X",
                        "absolute_url": "https://job.example/dup",
                        "content": "first",
                    }
                ]
            }
        }
    )
    src = dict(conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone())
    scan_source(conn, src, client=client, sleep=lambda *_: None)
    r2 = scan_source(conn, src, client=client, sleep=lambda *_: None)
    assert r2.inserted == 0  # already present
    assert r2.fetched == 1
    assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1


def test_scan_source_failure_records_error(
    db_with_source: tuple[sqlite3.Connection, int],
) -> None:
    conn, src_id = db_with_source

    # Always return 404. With short backoff, three failures and stop.
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = dict(conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone())
    result = scan_source(conn, src, client=client, backoff=(0, 0, 0), sleep=lambda *_: None)
    assert result.ok is False
    assert "404" in (result.error or "")
    src_row = conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone()
    assert src_row["last_error"] is not None
    assert "404" in src_row["last_error"]
    assert src_row["last_ok_at"] is None


def test_scan_source_retries_then_succeeds(
    db_with_source: tuple[sqlite3.Connection, int],
) -> None:
    conn, src_id = db_with_source
    counter = {"calls": 0}
    good = {"jobs": [{"title": "Eng", "absolute_url": "https://job.example/ok", "content": "JD"}]}

    def handler(_: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        if counter["calls"] < 3:
            return httpx.Response(500, text="oops")
        return httpx.Response(200, json=good)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = dict(conn.execute("SELECT * FROM ats_source WHERE id = ?", (src_id,)).fetchone())
    result = scan_source(conn, src, client=client, backoff=(0, 0, 0), sleep=lambda *_: None)
    assert result.ok is True
    assert counter["calls"] == 3


def test_scan_all_isolates_bad_source(tmp_db: sqlite3.Connection) -> None:
    tmp_db.execute(
        "INSERT INTO ats_source (ats_type, slug, company) VALUES ('greenhouse', 'good', 'Good')"
    )
    tmp_db.execute(
        "INSERT INTO ats_source (ats_type, slug, company) VALUES ('greenhouse', 'bad', 'Bad')"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if "/good/" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "title": "X",
                            "absolute_url": "https://job.example/g",
                            "content": "JD",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = scan_all(tmp_db, client=client, backoff=(0,), sleep=lambda *_: None)
    by_slug = {r.slug: r for r in results}
    assert by_slug["good"].ok is True
    assert by_slug["good"].inserted == 1
    assert by_slug["bad"].ok is False


def test_probe_returns_jobs_without_writing_db() -> None:
    client = _mock_client(
        {
            "https://boards-api.greenhouse.io/v1/boards/x/jobs": {
                "jobs": [{"title": "T", "absolute_url": "https://x.example/1", "content": "c"}]
            }
        }
    )
    rows = probe("greenhouse", "x", "X", client=client)
    assert len(rows) == 1
