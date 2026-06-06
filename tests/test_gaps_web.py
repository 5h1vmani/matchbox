"""The three surfaces re-added after the Jinja archive: add-a-role-by-hand +
score-new, targets/work-auth editing, and CV restyle."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox import assemble
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app
from matchbox.web.routes import packet, review_run


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    monkeypatch.setattr(packet, "_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(review_run, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(assemble, "RUNS_DIR", tmp_path / "runs")  # re_render_cv reads this
    with TestClient(create_app()) as c:
        yield c


def _conn() -> sqlite3.Connection:
    c = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(c)
    return c


# ── add a role by hand + score-new ──────────────────────────────────────────────


def test_add_job_by_hand_enriches_and_scores(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        json={
            "company": "Acme",
            "title": "Senior Backend Engineer",
            "url": "https://acme.example/jobs/be",
            "jd_text": "5+ years. We are unable to sponsor visas.",
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "new"

    conn = _conn()
    row = conn.execute("SELECT role_family, seniority, sponsorship FROM job WHERE id = ?", (r.json()["id"],)).fetchone()
    conn.close()
    assert row["role_family"] == "backend"  # enriched deterministically
    assert row["seniority"] == "senior"
    assert row["sponsorship"] == "none"

    # Duplicate url -> 409; missing fields -> 400.
    assert client.post("/api/jobs", json={"company": "Acme", "title": "BE", "url": "https://acme.example/jobs/be", "jd_text": "x"}).status_code == 409
    assert client.post("/api/jobs", json={"company": " ", "title": "", "url": "", "jd_text": ""}).status_code == 400

    # Score-new lifts it into Discover (offline/lexical: MATCHBOX_DISABLE_SEMANTIC is set by conftest).
    scored = client.post("/api/jobs/score-new").json()["scored"]
    assert scored >= 1
    assert any(role["company"] == "Acme" for role in client.get("/api/discovery/roles").json())


# ── targets + work authorization ─────────────────────────────────────────────────


def test_targets_roundtrip_with_work_auth(client: TestClient) -> None:
    assert client.get("/api/targets").json()["work_auth"]["needs_sponsorship"] is False
    saved = client.post(
        "/api/targets",
        json={
            "role_families": ["backend", " ml "],
            "locations": ["Remote"],
            "work_auth": {"citizenships": ["IN"], "needs_sponsorship": True, "has_clearance": False},
        },
    ).json()
    assert saved["role_families"] == ["backend", "ml"]
    assert saved["work_auth"] == {"citizenships": ["IN"], "needs_sponsorship": True, "has_clearance": False}
    # Persisted to the column the eligibility filter reads.
    conn = _conn()
    wa = json.loads(conn.execute("SELECT work_auth_json FROM target LIMIT 1").fetchone()[0])
    conn.close()
    assert wa["needs_sponsorship"] is True


# ── CV restyle ───────────────────────────────────────────────────────────────────


def test_restyle_re_renders_and_validates(client: TestClient, tmp_path: Path) -> None:
    conn = _conn()
    conn.execute("INSERT INTO job (id, company, title, url, jd_text) VALUES (1,'Acme','Eng','http://x/1','jd')")
    conn.execute("INSERT INTO run (id, status) VALUES ('2026-06-06-001','done')")
    conn.execute("INSERT INTO run_job (run_id, job_id, palette, font) VALUES ('2026-06-06-001',1,'slate','source-serif')")
    conn.execute("INSERT INTO application (id, job_id, run_id, stage) VALUES (1,1,'2026-06-06-001','saved')")
    conn.close()
    out = tmp_path / "runs" / "2026-06-06-001" / "output" / "1"
    out.mkdir(parents=True)
    (out / "cv.json").write_text(json.dumps({
        "schema_version": 1, "profile": {"name": "Dev", "contact": []}, "summary": "",
        "experiences": [], "projects": [], "skills": [], "education": [],
    }))

    r = client.post("/api/applications/1/restyle", json={"palette": "forest", "font": "inter"})
    assert r.status_code == 200
    assert (out / "cv.pdf").exists()

    conn = _conn()
    rj = conn.execute("SELECT palette, font FROM run_job WHERE run_id='2026-06-06-001'").fetchone()
    conn.close()
    assert rj["palette"] == "forest" and rj["font"] == "inter"

    # Unknown palette -> 400.
    assert client.post("/api/applications/1/restyle", json={"palette": "rainbow", "font": "inter"}).status_code == 400
