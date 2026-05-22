"""Tests for the onboarding, review, and targets routes."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Web TestClient with a fresh DB and inbox both rooted at tmp_path."""
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))

    # Point INBOX_DIR at the tmp dir for this test, then reset on teardown.
    from matchbox.web.routes import onboarding as ob

    original_inbox = ob.INBOX_DIR
    monkeypatch.setattr(ob, "INBOX_DIR", tmp_path / "inbox")

    app = create_app()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        # monkeypatch.setattr restores on its own
        assert tmp_path / "inbox" == ob.INBOX_DIR or original_inbox == ob.INBOX_DIR


def test_onboarding_index_renders(client_in_tmp: TestClient) -> None:
    r = client_in_tmp.get("/onboarding")
    assert r.status_code == 200
    assert "Onboarding" in r.text
    assert "ingest my files" in r.text


def test_upload_file_stages_it(client_in_tmp: TestClient, tmp_path: Path) -> None:
    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
    r = client_in_tmp.post(
        "/onboarding/upload",
        files={"files": ("my cv.pdf", fake_pdf, "application/pdf")},
    )
    assert r.status_code == 200
    assert "my_cv.pdf" in r.text  # sanitized

    staged = list((tmp_path / "inbox").iterdir())
    assert any(p.name == "my_cv.pdf" for p in staged)


def test_upload_rejects_disallowed_extension(client_in_tmp: TestClient) -> None:
    r = client_in_tmp.post(
        "/onboarding/upload",
        files={"files": ("danger.exe", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 415


def test_paste_saves_notes(client_in_tmp: TestClient, tmp_path: Path) -> None:
    r = client_in_tmp.post("/onboarding/paste", data={"text": "Built a thing once."})
    assert r.status_code == 200
    notes = list((tmp_path / "inbox").glob("notes-*.md"))
    assert len(notes) == 1
    assert notes[0].read_text(encoding="utf-8") == "Built a thing once."


def test_paste_rejects_empty(client_in_tmp: TestClient) -> None:
    r = client_in_tmp.post("/onboarding/paste", data={"text": "   "})
    assert r.status_code == 400


def test_remove_staged_deletes_file(client_in_tmp: TestClient, tmp_path: Path) -> None:
    (tmp_path / "inbox").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "inbox" / "notes.md"
    f.write_text("hi")
    r = client_in_tmp.delete("/onboarding/staged/notes.md")
    assert r.status_code == 200
    assert not f.exists()


def test_remove_staged_rejects_traversal(client_in_tmp: TestClient) -> None:
    r = client_in_tmp.delete("/onboarding/staged/..%2Fmatchbox.db")
    # Sanitizer reduces this to a single non-path leaf; if no such file
    # exists in inbox it 404s. Either way, no escape happens.
    assert r.status_code in (404, 400)


def test_targets_form_round_trip(client_in_tmp: TestClient) -> None:
    r = client_in_tmp.get("/targets")
    assert r.status_code == 200

    r2 = client_in_tmp.post(
        "/targets",
        data={
            "role_families": "fde\nml-platform",
            "dream_companies": "Modal, Anthropic",
            "locations": "remote",
            "comp_min": "180000",
            "comp_max": "260000",
            "comp_currency": "USD",
            "exclusions": "defense",
        },
    )
    assert r2.status_code == 200
    assert "Saved" in r2.text

    # GET again shows persisted values
    page = client_in_tmp.get("/targets").text
    assert "fde" in page
    assert "Modal" in page
    assert "180000" in page


def test_review_screen_after_ingest(client_in_tmp: TestClient, tmp_path: Path) -> None:
    """End-to-end: brain ingests a payload, user opens review, verifies."""
    from matchbox.onboarding.ingest_cli import main as ingest_main

    payload = {
        "schema_version": 1,
        "experiences": [
            {
                "company": "Modal",
                "role": "FDE",
                "bullets": [
                    {"text": "Shipped a thing.", "tags": []},
                    {"text": "Shipped another thing.", "tags": []},
                ],
            }
        ],
        "projects": [{"name": "Matchbox", "text": "a project"}],
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload))

    rc = ingest_main(["--file", str(payload_path), "--db", str(tmp_path / "matchbox.db")])
    assert rc == 0

    page = client_in_tmp.get("/review").text
    assert "Shipped a thing." in page
    assert "unverified" in page

    # Pull a bullet id and verify it
    m = re.search(r'review-bullet-(\d+)"', page)
    assert m is not None
    bullet_id = int(m.group(1))

    r = client_in_tmp.post(f"/review/bullets/{bullet_id}/verify")
    assert r.status_code == 200
    assert "verified" in r.text


def test_verify_all_in_experience(client_in_tmp: TestClient, tmp_path: Path) -> None:
    from matchbox.onboarding.ingest_cli import main as ingest_main

    payload = {
        "schema_version": 1,
        "experiences": [
            {
                "company": "X",
                "role": "Y",
                "bullets": [
                    {"text": "one"},
                    {"text": "two"},
                    {"text": "three"},
                ],
            }
        ],
    }
    payload_path = tmp_path / "p.json"
    payload_path.write_text(json.dumps(payload))
    ingest_main(["--file", str(payload_path), "--db", str(tmp_path / "matchbox.db")])

    page = client_in_tmp.get("/review").text
    exp_id = int(re.search(r'review-experience-(\d+)"', page).group(1))  # type: ignore[union-attr]

    r = client_in_tmp.post(f"/review/experiences/{exp_id}/verify-all")
    assert r.status_code == 200
    assert r.text.count("verified") >= 3
    assert "unverified" not in r.text
