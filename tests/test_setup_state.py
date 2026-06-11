"""GET /api/setup/state — the onboarding rail's seven derived booleans."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import matchbox.core.db as db
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app
from matchbox.web.routes import onboarding

STEP_IDS = ["history", "verify", "profile", "targets", "job", "tailor", "apply"]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An app whose people/ tree AND inbox/ live under tmp_path, never the real ones."""
    monkeypatch.delenv("MATCHBOX_DB", raising=False)
    monkeypatch.delenv("MATCHBOX_PROFILE", raising=False)
    monkeypatch.setattr(db, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(onboarding, "INBOX_DIR", tmp_path / "inbox")
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A handle on the same DB the app serves (the default profile under tmp_path)."""
    c = connect(tmp_path / "people" / db.DEFAULT_PROFILE / "matchbox.db")
    migrate(c)
    yield c
    c.close()


def state(client: TestClient) -> dict[str, Any]:
    r = client.get("/api/setup/state")
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    return body


def step(body: dict[str, Any], step_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(s for s in body["steps"] if s["id"] == step_id)
    return found


def add_bullet(conn: sqlite3.Connection, *, verified: bool) -> int:
    eid = conn.execute(
        "INSERT INTO experience (company, role) VALUES ('Acme', 'Engineer')"
    ).lastrowid
    bid = conn.execute(
        "INSERT INTO bullet (experience_id, text, facts_verified) VALUES (?, ?, ?)",
        (eid, "Shipped a thing", int(verified)),
    ).lastrowid
    assert bid is not None
    return bid


def add_job(conn: sqlite3.Connection, url: str = "https://jobs.example/1") -> int:
    jid = conn.execute(
        "INSERT INTO job (company, title, url, jd_text) VALUES ('Acme', 'Engineer', ?, 'JD')",
        (url,),
    ).lastrowid
    assert jid is not None
    return jid


def test_empty_db_all_undone(client: TestClient) -> None:
    body = state(client)
    assert [s["id"] for s in body["steps"]] == STEP_IDS
    assert body["current"] == 0
    assert all(not s["done"] for s in body["steps"])
    assert [s["active"] for s in body["steps"]] == [True] + [False] * 6


def test_bullet_completes_history(client: TestClient, conn: sqlite3.Connection) -> None:
    add_bullet(conn, verified=False)
    body = state(client)
    assert step(body, "history")["done"] is True
    assert step(body, "verify")["done"] is False
    assert step(body, "verify")["partial"] is False  # nothing verified yet
    assert body["current"] == 1
    assert step(body, "verify")["active"] is True


def test_staged_inbox_file_completes_history(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "old-cv.pdf").write_bytes(b"%PDF-1.4")
    body = state(client)
    assert step(body, "history")["done"] is True
    assert body["current"] == 1


def test_verify_needs_every_bullet_confirmed(client: TestClient, conn: sqlite3.Connection) -> None:
    add_bullet(conn, verified=True)
    add_bullet(conn, verified=False)
    body = state(client)
    assert step(body, "verify")["done"] is False
    assert step(body, "verify")["partial"] is True  # some verified, some pending
    conn.execute("UPDATE bullet SET facts_verified = 1")
    body = state(client)
    assert step(body, "verify")["done"] is True
    assert step(body, "verify")["partial"] is False
    assert body["current"] == 2


def test_profile_needs_a_name(client: TestClient, conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO profile (full_name) VALUES ('  ')")
    assert step(state(client), "profile")["done"] is False
    conn.execute("UPDATE profile SET full_name = 'Shiva Padakanti'")
    assert step(state(client), "profile")["done"] is True


def test_steps_complete_independently(client: TestClient, conn: sqlite3.Connection) -> None:
    add_job(conn)  # step 5 without steps 1-4
    body = state(client)
    assert step(body, "job")["done"] is True
    assert step(body, "targets")["done"] is False
    assert body["current"] == 0  # first not-done step is still history
    assert step(body, "history")["active"] is True
    assert step(body, "job")["active"] is False


def test_tailor_via_run_or_cv_backed_application(
    client: TestClient, conn: sqlite3.Connection
) -> None:
    jid = add_job(conn)
    conn.execute(
        "INSERT INTO application (job_id, stage, cv_path) VALUES (?, 'saved', ?)",
        (jid, "runs/2026-06-11-001/output/1/cv.pdf"),
    )
    assert step(state(client), "tailor")["done"] is True
    assert step(state(client), "apply")["done"] is False


def test_full_sequence_advances_to_done(client: TestClient, conn: sqlite3.Connection) -> None:
    add_bullet(conn, verified=True)
    conn.execute("INSERT INTO profile (full_name) VALUES ('Shiva Padakanti')")
    conn.execute("INSERT INTO target DEFAULT VALUES")
    jid = add_job(conn)
    conn.execute("INSERT INTO run (id) VALUES ('2026-06-11-001')")
    conn.execute(
        "INSERT INTO application (job_id, stage, applied_at) VALUES (?, 'applied', '2026-06-11')",
        (jid,),
    )
    body = state(client)
    assert all(s["done"] for s in body["steps"])
    assert all(not s["active"] for s in body["steps"])
    assert body["current"] == 7
