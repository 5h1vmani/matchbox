"""Tests for the M6 handoff-loop routes — review-run, polling card,
mark-applied, and sandboxed PDF serving.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))

    from matchbox.web.routes import review_run as rr_mod

    monkeypatch.setattr(rr_mod, "RUNS_DIR", tmp_path / "runs")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed_run_and_job(tmp_path: Path) -> tuple[str, int]:
    """Seed a run + run_job + job directly in the DB (skipping the inbox UI)."""
    import os

    from matchbox.core.db import connect
    from matchbox.core.migrations import migrate

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, location, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'selected')",
        ("Modal", "FDE", "https://x/1", "JD", "https://apply/1", "Remote"),
    )
    job_id = cur.lastrowid
    assert job_id is not None
    run_id = "2026-05-22-001"
    conn.execute("INSERT INTO run (id, status) VALUES (?, 'queued')", (run_id,))
    conn.execute(
        "INSERT INTO run_job (run_id, job_id, want_cv, want_cover, palette, font) "
        "VALUES (?, ?, 1, 0, 'slate', 'source-serif')",
        (run_id, job_id),
    )
    conn.close()
    return run_id, job_id


def _write_status(tmp_path: Path, run_id: str, payload: dict) -> None:
    p = tmp_path / "runs" / run_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_review_run_renders_pending_when_no_status(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    r = client.get(f"/review-run/{run_id}")
    assert r.status_code == 200
    assert run_id in r.text
    assert "Modal" in r.text
    assert "pending" in r.text  # default cv_status before status.json exists


def test_review_run_reflects_status_json(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    _write_status(
        tmp_path,
        run_id,
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": "done",
            "jobs": [
                {
                    "job_id": job_id,
                    "cv_status": "done",
                    "cover_status": "skipped",
                    "cv_path": f"runs/{run_id}/output/{job_id}/cv.pdf",
                    "cover_path": None,
                    "gaps": ["JD asks for Terraform"],
                    "notes": "Picked 8 bullets across 2 roles.",
                }
            ],
        },
    )
    r = client.get(f"/review-run/{run_id}")
    assert r.status_code == 200
    assert "done" in r.text
    assert "Terraform" in r.text


def test_card_poll_returns_just_one_card(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    r = client.get(f"/review-run/{run_id}/jobs/{job_id}/card")
    assert r.status_code == 200
    assert "Modal" in r.text
    assert f"job-card-{job_id}" in r.text


def test_schema_version_mismatch_is_409(client: TestClient, tmp_path: Path) -> None:
    run_id, _ = _seed_run_and_job(tmp_path)
    _write_status(
        tmp_path, run_id, {"schema_version": 99, "run_id": run_id, "status": "done", "jobs": []}
    )
    r = client.get(f"/review-run/{run_id}")
    assert r.status_code == 409


def test_mark_applied_records_application(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    r = client.post(
        f"/review-run/{run_id}/jobs/{job_id}/applied",
        data={"cv_path": f"runs/{run_id}/output/{job_id}/cv.pdf"},
    )
    assert r.status_code == 200
    assert "applied" in r.text

    import os

    from matchbox.core.db import connect

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    rows = conn.execute(
        "SELECT status, applied_at, cv_path FROM application WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "applied"
    assert rows[0]["applied_at"] is not None
    job_status = conn.execute("SELECT status FROM job WHERE id = ?", (job_id,)).fetchone()[0]
    assert job_status == "applied"
    conn.close()


def test_pdf_serving_returns_file(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    out = tmp_path / "runs" / run_id / "output" / str(job_id)
    out.mkdir(parents=True, exist_ok=True)
    pdf_bytes = b"%PDF-1.4 fake content"
    (out / "cv.pdf").write_bytes(pdf_bytes)

    r = client.get(f"/runs/{run_id}/output/{job_id}/cv.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_pdf_serving_rejects_traversal(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    (tmp_path / "runs" / run_id / "output" / str(job_id)).mkdir(parents=True, exist_ok=True)
    # The route validates `/` is not in filename — anything else is route-segment'ed by FastAPI.
    r = client.get(f"/runs/{run_id}/output/{job_id}/.env")
    assert r.status_code in (400, 404)


def test_pdf_serving_rejects_unsupported_type(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    out = tmp_path / "runs" / run_id / "output" / str(job_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "secret.exe").write_bytes(b"x")
    r = client.get(f"/runs/{run_id}/output/{job_id}/secret.exe")
    assert r.status_code == 415


def test_runs_index_lists_run(client: TestClient, tmp_path: Path) -> None:
    run_id, _ = _seed_run_and_job(tmp_path)
    r = client.get("/runs")
    assert r.status_code == 200
    assert run_id in r.text


def test_unknown_run_is_404(client: TestClient) -> None:
    r = client.get("/review-run/9999-99-99-999")
    assert r.status_code == 404
