"""Apply packet + onboarding/review JSON APIs (the React replacements)."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app
from matchbox.web.routes import onboarding, packet, review_run


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    monkeypatch.setattr(packet, "_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(review_run, "RUNS_DIR", tmp_path / "runs")  # the file-serving route
    monkeypatch.setattr(onboarding, "INBOX_DIR", tmp_path / "inbox")
    with TestClient(create_app()) as c:
        yield c


def _seed(tmp_path: Path) -> None:
    conn: sqlite3.Connection = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    conn.execute("INSERT INTO job (id, company, title, url, jd_text) VALUES (1,'Acme','Eng','http://x/1','jd')")
    conn.execute("INSERT INTO run (id, status) VALUES ('2026-06-06-001','done')")
    conn.execute("INSERT INTO run_job (run_id, job_id) VALUES ('2026-06-06-001', 1)")
    conn.execute("INSERT INTO application (id, job_id, run_id, stage) VALUES (1, 1, '2026-06-06-001', 'saved')")
    conn.close()
    out = tmp_path / "runs" / "2026-06-06-001" / "output" / "1"
    out.mkdir(parents=True)
    (out / "cv.pdf").write_bytes(b"%PDF-1.4 fake")
    (out / "changes.md").write_text("# changes")
    (out / "coverage.json").write_text(json.dumps({"semantic": {"must_haves": [{"text": "a", "band": "covered"}]}}))


def test_packet_view_model_and_submit(client: TestClient, tmp_path: Path) -> None:
    _seed(tmp_path)
    pkt = client.get("/api/applications/1/packet").json()
    assert pkt["company"] == "Acme"
    assert pkt["resume"]["cvUrl"] == "/runs/2026-06-06-001/output/1/cv.pdf"
    assert pkt["resume"]["changesUrl"].endswith("changes.md")
    assert pkt["coverage"]["semantic"]["must_haves"][0]["band"] == "covered"
    assert pkt["cover"]["text"] is None  # no cover.txt yet

    # The sandboxed file route serves the artifact.
    assert client.get(pkt["resume"]["cvUrl"]).status_code == 200

    # Submit -> applied + applied_at + a +7d follow-up reminder.
    app = client.post("/api/applications/1/submit").json()
    assert app["stage"] == "applied"
    assert app["nextAction"]["kind"] == "followup"
    assert app["nextAction"]["due"] == 7
    assert client.post("/api/applications/999/submit").status_code == 404


def test_packet_404_for_missing_app(client: TestClient, tmp_path: Path) -> None:
    _seed(tmp_path)
    assert client.get("/api/applications/42/packet").status_code == 404


# ── onboarding JSON ──────────────────────────────────────────────────────────────


def test_onboarding_upload_paste_and_remove(client: TestClient) -> None:
    assert client.get("/api/onboarding").json()["staged"] == []
    r = client.post("/api/onboarding/upload", files={"files": ("cv.txt", b"hello", "text/plain")})
    names = [f["name"] for f in r.json()]
    assert "cv.txt" in names
    # Rejected extension.
    assert client.post(
        "/api/onboarding/upload", files={"files": ("x.exe", b"nope", "application/octet-stream")}
    ).status_code == 415
    # Paste -> a notes-*.md staged.
    staged = client.post("/api/onboarding/paste", data={"text": "some notes"}).json()
    assert any(f["name"].startswith("notes-") for f in staged)
    assert client.delete("/api/onboarding/staged/cv.txt").status_code == 200


# ── review JSON ──────────────────────────────────────────────────────────────────


def test_review_verify_flow(client: TestClient, tmp_path: Path) -> None:
    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    conn.execute("INSERT INTO experience (id, company, role) VALUES (1, 'Acme', 'Eng')")
    conn.execute("INSERT INTO bullet (id, experience_id, text, facts_verified) VALUES (1, 1, 'Did a thing.', 0)")
    conn.execute("INSERT INTO bullet (id, experience_id, text, facts_verified) VALUES (2, 1, 'Did another.', 0)")
    conn.close()

    state = client.get("/api/review").json()
    assert state["unverifiedBullets"] == 2
    assert client.post("/api/review/bullets/1/verify").json()["verified"] is True
    assert client.get("/api/review").json()["unverifiedBullets"] == 1
    # Verify-all clears the rest.
    client.post("/api/review/verify-all")
    assert client.get("/api/review").json()["unverifiedBullets"] == 0


