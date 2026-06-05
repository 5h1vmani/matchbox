"""Answer library: the DAL, the /api/answers router, and ingest of Q&A."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.answers import repo
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.onboarding.ingest_cli import ingest
from matchbox.web.app import create_app


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "a.db")
    migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    with TestClient(create_app()) as c:
        yield c


# ── DAL ──────────────────────────────────────────────────────────────────────────


def test_dal_crud_verify_and_usage(conn: sqlite3.Connection) -> None:
    aid = repo.create(conn, question="Why us?", answer="I admire the ledger work.", category="why-us")
    row = repo.get(conn, aid)
    assert row is not None
    assert row["verified"] is False  # lands unverified, like a bullet
    assert row["usedCount"] == 0

    # Verify it (the /review confirm).
    repo.update(conn, aid, facts_verified=True)
    assert repo.get(conn, aid)["verified"] is True

    # Usage bumps on selection.
    repo.mark_used(conn, aid)
    repo.mark_used(conn, aid)
    assert repo.get(conn, aid)["usedCount"] == 2

    # Verified filter.
    repo.create(conn, question="Salary?", answer="Open to a fair range.")
    assert len(repo.list_all(conn)) == 2
    assert len(repo.list_all(conn, verified=True)) == 1

    repo.delete(conn, aid)
    assert repo.get(conn, aid) is None


# ── ingest ───────────────────────────────────────────────────────────────────────


def test_ingest_answers_land_unverified(conn: sqlite3.Connection) -> None:
    payload = {
        "schema_version": 1,
        "answers": [
            {"question": "Why us?", "answer": "The mission fits.", "category": "why-us",
             "source_file": "inbox/notes.md"},
        ],
    }
    counts = ingest(payload, conn)
    assert counts["answers"] == 1
    rows = repo.list_all(conn)
    assert len(rows) == 1
    assert rows[0]["verified"] is False
    assert rows[0]["sourceFile"] == "inbox/notes.md"


# ── router ───────────────────────────────────────────────────────────────────────


def test_router_roundtrip(client: TestClient) -> None:
    r = client.post("/api/answers", json={"question": "Why us?", "answer": "The ledger work."})
    assert r.status_code == 200
    aid = r.json()["id"]
    assert r.json()["verified"] is False

    # Verify via PATCH.
    assert client.patch(f"/api/answers/{aid}", json={"verified": True}).json()["verified"] is True
    # Use bumps the count.
    assert client.post(f"/api/answers/{aid}/use").json()["usedCount"] == 1
    # Verified filter on list.
    assert len(client.get("/api/answers?verified=1").json()) == 1
    # Validation: empty question/answer rejected.
    assert client.post("/api/answers", json={"question": " ", "answer": " "}).status_code == 400

    assert client.delete(f"/api/answers/{aid}").status_code == 200
    assert client.patch(f"/api/answers/{aid}", json={"verified": True}).status_code == 404
