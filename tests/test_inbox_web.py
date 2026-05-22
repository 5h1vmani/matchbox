"""End-to-end tests for the /inbox triage UI."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))

    from matchbox.scoring import runs as runs_mod

    monkeypatch.setattr(runs_mod, "RUNS_DIR", tmp_path / "runs")

    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed_jobs(client: TestClient) -> list[int]:
    # Reach into the DB directly so we don't have to drive an ATS poller here.
    import os

    from matchbox.core.db import connect
    from matchbox.core.migrations import migrate

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    try:
        conn.execute(
            "INSERT INTO target (role_families_json, dream_companies_json, locations_json, comp_json, exclusions_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                '["forward-deployed-engineer"]',
                '["Anthropic"]',
                '["remote"]',
                "{}",
                "[]",
            ),
        )
        conn.execute(
            "INSERT INTO job (company, title, url, jd_text, apply_url, location, status) VALUES (?, ?, ?, ?, ?, ?, 'new')",
            (
                "Anthropic",
                "Forward Deployed Engineer",
                "https://x/1",
                "Python.",
                "https://apply/1",
                "Remote",
            ),
        )
        conn.execute(
            "INSERT INTO job (company, title, url, jd_text, apply_url, location, status) VALUES (?, ?, ?, ?, ?, ?, 'new')",
            ("Random", "PHP Dev", "https://x/2", "PHP.", "https://apply/2", "Albuquerque"),
        )
        return [r[0] for r in conn.execute("SELECT id FROM job ORDER BY id").fetchall()]
    finally:
        conn.close()


def test_inbox_index_renders(client: TestClient) -> None:
    r = client.get("/inbox")
    assert r.status_code == 200
    assert "Inbox" in r.text


def test_score_all_then_inbox_shows_scores(client: TestClient) -> None:
    _seed_jobs(client)
    r = client.post("/inbox/score-all")
    assert r.status_code == 200
    assert "scored 2 new jobs" in r.text

    page = client.get("/inbox").text
    # The FDE/Anthropic/Remote job should outscore the PHP/Random/on-site one.
    # Pull score columns in row order.
    scores = re.findall(r'font-mono">\s*([\d.]+)\s*<', page)
    assert len(scores) >= 2
    assert float(scores[0]) > float(scores[1])


def test_start_run_writes_work_queue(client: TestClient, tmp_path: Path) -> None:
    job_ids = _seed_jobs(client)
    client.post("/inbox/score-all")

    r = client.post(
        "/runs",
        data={
            "job_ids": [str(j) for j in job_ids],
            "want_cv": [str(job_ids[0])],
            "want_cover": [str(job_ids[0])],
            "palette": "slate",
            "font": "source-serif",
        },
    )
    assert r.status_code == 200
    assert "queued" in r.text.lower()

    run_id_match = re.search(r"Run (\d{4}-\d{2}-\d{2}-\d{3})", r.text)
    assert run_id_match is not None
    run_id = run_id_match.group(1)
    work_queue = tmp_path / "runs" / run_id / "work-queue.json"
    assert work_queue.exists()

    payload = json.loads(work_queue.read_text())
    assert payload["schema_version"] == 1
    assert payload["run_id"] == run_id
    assert len(payload["jobs"]) == 1  # only job_ids[0] selected
    assert payload["jobs"][0]["want_cv"] is True
    assert payload["jobs"][0]["want_cover"] is True


def test_start_run_rejects_no_selection(client: TestClient) -> None:
    job_ids = _seed_jobs(client)
    r = client.post(
        "/runs",
        data={
            "job_ids": [str(j) for j in job_ids],
            "palette": "slate",
            "font": "source-serif",
            # no want_cv, no want_cover toggles
        },
    )
    assert r.status_code == 400
    assert "at least one" in r.text


def test_start_run_rejects_unknown_palette(client: TestClient) -> None:
    job_ids = _seed_jobs(client)
    r = client.post(
        "/runs",
        data={
            "job_ids": [str(j) for j in job_ids],
            "want_cv": [str(job_ids[0])],
            "palette": "rainbow",
            "font": "source-serif",
        },
    )
    assert r.status_code == 400


def test_skip_job_moves_to_skipped(client: TestClient) -> None:
    job_ids = _seed_jobs(client)
    r = client.post(f"/inbox/jobs/{job_ids[0]}/status", data={"to": "skipped"})
    assert r.status_code == 200
    assert "skipped" in r.text

    page = client.get("/inbox?status=skipped").text
    # Top job is the FDE; assert the row shows under the skipped filter.
    assert "Forward Deployed Engineer" in page


def test_reject_then_reopen_round_trips(client: TestClient) -> None:
    job_ids = _seed_jobs(client)
    client.post(f"/inbox/jobs/{job_ids[0]}/status", data={"to": "rejected"})
    page = client.get("/inbox?status=rejected").text
    assert "Forward Deployed Engineer" in page

    r = client.post(f"/inbox/jobs/{job_ids[0]}/status", data={"to": "scored"})
    assert r.status_code == 200
    # Comes back to the default (open) view; rejected filter no longer shows it.
    assert "Forward Deployed Engineer" not in client.get("/inbox?status=rejected").text


def test_set_status_rejects_unknown_transition(client: TestClient) -> None:
    job_ids = _seed_jobs(client)
    r = client.post(f"/inbox/jobs/{job_ids[0]}/status", data={"to": "tailored"})
    assert r.status_code == 400


def test_set_status_rejects_tailored_or_applied_source(client: TestClient) -> None:
    """Jobs that have been tailored are not user-skippable from /inbox."""
    job_ids = _seed_jobs(client)
    import os

    from matchbox.core.db import connect

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    conn.execute("UPDATE job SET status = 'tailored' WHERE id = ?", (job_ids[0],))
    conn.close()
    r = client.post(f"/inbox/jobs/{job_ids[0]}/status", data={"to": "skipped"})
    assert r.status_code == 409


def test_set_status_unknown_job_is_404(client: TestClient) -> None:
    r = client.post("/inbox/jobs/99999/status", data={"to": "skipped"})
    assert r.status_code == 404


def test_status_filter_narrows_list(client: TestClient) -> None:
    _seed_jobs(client)
    client.post("/inbox/score-all")  # all become 'scored'
    page = client.get("/inbox?status=new").text
    # No new jobs after scoring.
    assert "Forward Deployed Engineer" not in page
    page2 = client.get("/inbox?status=scored").text
    assert "Forward Deployed Engineer" in page2
