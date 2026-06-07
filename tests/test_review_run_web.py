"""Run artifacts: sandboxed file serving, run deletion, status validation.

The Jinja review-run progress UI was archived in the all-React migration; these
cover what remains in review_run.py (the non-presentational core the Apply packet
relies on).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app
from matchbox.web.routes.review_run import validate_status_payload


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    from matchbox.web.routes import review_run as rr_mod

    monkeypatch.setattr(rr_mod, "RUNS_DIR", tmp_path / "runs")
    with TestClient(create_app()) as c:
        yield c


def _seed_run_and_job(tmp_path: Path) -> tuple[str, int]:
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


# ── sandboxed file serving (security) ────────────────────────────────────────────


def test_pdf_serving_returns_file(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    out = tmp_path / "runs" / run_id / "output" / str(job_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cv.pdf").write_bytes(b"%PDF-1.4 fake content")
    r = client.get(f"/runs/{run_id}/output/{job_id}/cv.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_pdf_serving_rejects_dotfiles(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    (tmp_path / "runs" / run_id / "output" / str(job_id)).mkdir(parents=True, exist_ok=True)
    assert client.get(f"/runs/{run_id}/output/{job_id}/.env").status_code == 400


def test_pdf_serving_rejects_path_traversal(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    base = tmp_path / "runs" / run_id / "output" / str(job_id)
    base.mkdir(parents=True, exist_ok=True)
    secret = tmp_path / "runs" / run_id / "secret.txt"
    secret.write_text("don't leak this")
    r = client.get(f"/runs/{run_id}/output/{job_id}/..%2Fsecret.txt")
    assert r.status_code in (400, 404)
    assert b"don't leak this" not in r.content


def test_pdf_serving_rejects_unsupported_type(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    out = tmp_path / "runs" / run_id / "output" / str(job_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "secret.exe").write_bytes(b"x")
    assert client.get(f"/runs/{run_id}/output/{job_id}/secret.exe").status_code == 415


# ── run deletion ─────────────────────────────────────────────────────────────────


def test_delete_run_removes_rows_and_dir(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_and_job(tmp_path)
    out_dir = tmp_path / "runs" / run_id / "output" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cv.pdf").write_bytes(b"%PDF-fake")

    assert client.delete(f"/runs/{run_id}").status_code == 200
    assert not (tmp_path / "runs" / run_id).exists()

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    assert conn.execute("SELECT 1 FROM run WHERE id = ?", (run_id,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM run_job WHERE run_id = ?", (run_id,)).fetchone() is None
    # The job row stays, but its status falls back to 'scored'.
    assert (
        conn.execute("SELECT status FROM job WHERE id = ?", (job_id,)).fetchone()["status"]
        == "scored"
    )
    conn.close()


def test_delete_unknown_run_is_404(client: TestClient) -> None:
    assert client.delete("/runs/no-such-id").status_code == 404


# ── status.json schema validation ────────────────────────────────────────────────


def test_validate_status_payload() -> None:
    ok = {"schema_version": 1, "run_id": "2026-05-22-001", "status": "done", "jobs": []}
    assert validate_status_payload(ok) == []
    bad = {"schema_version": 1, "run_id": "r", "status": "not-a-status", "jobs": []}
    assert validate_status_payload(bad)  # non-empty -> schema errors surfaced
