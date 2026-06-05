"""Tests for M7 — cover-letter render and the palette/font restyle path."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.assemble import assemble_cover, re_render_cv
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app


@pytest.fixture(autouse=True)
def _isolate_dbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-point the DB and RUNS_DIR for every test in this module."""
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    from matchbox import assemble as assemble_mod
    from matchbox.web.routes import review_run as rr_mod

    monkeypatch.setattr(assemble_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(rr_mod, "RUNS_DIR", tmp_path / "runs")


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed_run_with_finished_cv(tmp_path: Path) -> tuple[str, int]:
    """Seed a run + job + a finished cv.json in the output dir. This is
    the state restyle and cover-letter both depend on."""
    import os

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    conn.execute(
        "INSERT INTO profile (full_name, email, location, links_json, headline) VALUES (?, ?, ?, ?, ?)",
        ("Shiva Padakanti", "shiva@example.com", "Remote", "[]", "Generalist engineer"),
    )
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, location, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'tailored')",
        ("Modal", "FDE", "https://x/1", "JD", "https://apply/1", "Remote"),
    )
    job_id = cur.lastrowid
    assert job_id is not None
    run_id = "2026-05-22-001"
    conn.execute("INSERT INTO run (id, status) VALUES (?, 'done')", (run_id,))
    conn.execute(
        "INSERT INTO run_job (run_id, job_id, want_cv, want_cover, palette, font) "
        "VALUES (?, ?, 1, 1, 'slate', 'source-serif')",
        (run_id, job_id),
    )
    conn.close()

    out_dir = tmp_path / "runs" / run_id / "output" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_json = {
        "schema_version": 1,
        "profile": {
            "name": "Shiva Padakanti",
            "headline": "Generalist engineer",
            "contact": ["shiva@example.com", "Remote"],
        },
        "summary": "Engineer.",
        "experiences": [
            {
                "company": "Modal",
                "role": "FDE",
                "start_date": "2024-01",
                "end_date": "present",
                "location": "Remote",
                "bullets": ["Shipped streaming inference.", "Operated Kubernetes."],
            }
        ],
        "projects": [],
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "education": [],
    }
    (out_dir / "cv.json").write_text(json.dumps(cv_json, indent=2))
    return run_id, job_id


def test_re_render_cv_changes_palette(tmp_path: Path) -> None:
    run_id, job_id = _seed_run_with_finished_cv(tmp_path)
    pdf, drift = re_render_cv(run_id=run_id, job_id=job_id, palette="forest", font="inter")
    assert pdf.exists()
    assert pdf.stat().st_size > 2000
    # Seed has no _selected_bullets fingerprints, so drift is empty (no
    # baseline to diff against). drift only triggers when assemble_one
    # wrote the fingerprints.
    assert drift == []


def test_re_render_cv_missing_cv_json_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        re_render_cv(run_id="no-such", job_id=1, palette="slate", font="source-serif")


def test_restyle_route_re_renders(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_with_finished_cv(tmp_path)
    # Write a status.json so the card thinks cv is done.
    (tmp_path / "runs" / run_id / "status.json").write_text(
        json.dumps(
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
                    }
                ],
            }
        )
    )
    r = client.post(
        f"/review-run/{run_id}/jobs/{job_id}/restyle",
        data={"palette": "forest", "font": "inter"},
    )
    assert r.status_code == 200
    assert (tmp_path / "runs" / run_id / "output" / str(job_id) / "cv.pdf").exists()

    # The run_job row was updated
    import os

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    row = conn.execute(
        "SELECT palette, font FROM run_job WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchone()
    assert row["palette"] == "forest"
    assert row["font"] == "inter"
    conn.close()


def test_restyle_route_rejects_unknown_palette(client: TestClient, tmp_path: Path) -> None:
    run_id, job_id = _seed_run_with_finished_cv(tmp_path)
    r = client.post(
        f"/review-run/{run_id}/jobs/{job_id}/restyle",
        data={"palette": "rainbow", "font": "inter"},
    )
    assert r.status_code == 400


def test_assemble_cover_renders_pdf(tmp_path: Path) -> None:
    run_id, job_id = _seed_run_with_finished_cv(tmp_path)
    out_dir = tmp_path / "runs" / run_id / "output" / str(job_id)
    (out_dir / "cover.txt").write_text(
        "Modal builds the tools I want to use. I have built and operated\n"
        "production ML systems for two years, and I would bring that to the FDE role.\n"
        "\n"
        "I would welcome the chance to talk further.",
        encoding="utf-8",
    )

    import os

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    pdf = assemble_cover(
        conn=conn,
        run_id=run_id,
        job_id=job_id,
        palette="slate",
        font="source-serif",
    )
    conn.close()
    assert pdf.exists()
    assert pdf.stat().st_size > 2000

    # Extracted text has the candidate's name and the body.
    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)
    assert "Shiva Padakanti" in text
    assert "Modal" in text
    assert "production ML systems" in text


def test_assemble_cover_missing_body_raises(tmp_path: Path) -> None:
    run_id, job_id = _seed_run_with_finished_cv(tmp_path)
    import os

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    with pytest.raises(FileNotFoundError):
        assemble_cover(
            conn=conn, run_id=run_id, job_id=job_id, palette="slate", font="source-serif"
        )
    conn.close()
