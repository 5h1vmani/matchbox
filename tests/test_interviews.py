"""Interview loop: rounds DAL, debrief capture, Round[] serialization, the
/api routes, and prior-debrief carry into the prep task."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.interviews import repo
from matchbox.web.app import create_app


def _app(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO job (id, company, title, url, jd_text) "
        "VALUES (1, 'Acme', 'Engineer', 'http://x/1', 'jd')"
    )
    conn.execute("INSERT INTO application (id, job_id, stage) VALUES (1, 1, 'phone')")
    return 1


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "i.db")
    migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    with TestClient(create_app()) as c:
        yield c


def test_round_and_debrief_roundtrip(conn: sqlite3.Connection) -> None:
    app_id = _app(conn)
    rid = repo.create_round(conn, app_id, kind="recruiter", focus="comp + logistics")
    rounds = repo.rounds_for(conn, app_id)
    assert len(rounds) == 1
    assert rounds[0]["kind"] == "recruiter"
    assert rounds[0]["status"] == "scheduled"
    assert rounds[0]["debrief"] is None

    # One-tap debrief marks the round done and inlines on the Round.
    repo.upsert_debrief(conn, rid, sentiment="good", notes="warm, moving to HM")
    r = repo.get_round(conn, rid)
    assert r is not None
    assert r["status"] == "done"
    assert r["debrief"]["sentiment"] == "good"

    # Upsert (one per round) -- second capture overwrites, not duplicates.
    repo.upsert_debrief(conn, rid, sentiment="mixed", notes="revised read")
    assert repo.get_round(conn, rid)["debrief"]["sentiment"] == "mixed"

    # prior_debriefs is the assisted context for the next prep.
    pri = repo.prior_debriefs(conn, app_id)
    assert pri == [
        {
            "kind": "recruiter",
            "focus": "comp + logistics",
            "sentiment": "mixed",
            "notes": "revised read",
        }
    ]


def test_invalid_kind_and_sentiment_rejected(conn: sqlite3.Connection) -> None:
    app_id = _app(conn)
    with pytest.raises(ValueError):
        repo.create_round(conn, app_id, kind="coffee-chat")
    rid = repo.create_round(conn, app_id, kind="onsite")
    with pytest.raises(ValueError):
        repo.upsert_debrief(conn, rid, sentiment="ecstatic")


def test_routes_and_prep_carries_prior_debrief(client: TestClient) -> None:
    client.post("/api/agent-tasks", json={"kind": "noop"})  # warm the lazy migrate
    # Seed an application directly through the same DB the client uses.
    import os

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    _app(conn)
    conn.close()

    rid = client.post(
        "/api/applications/1/rounds", json={"kind": "hm", "focus": "system design"}
    ).json()["id"]
    assert client.get("/api/applications/1/rounds").json()[0]["kind"] == "hm"
    # Bad kind -> 400.
    assert client.post("/api/applications/1/rounds", json={"kind": "bogus"}).status_code == 400

    deb = client.post(
        f"/api/rounds/{rid}/debrief", json={"sentiment": "tough", "notes": "deep dive"}
    )
    assert deb.json()["status"] == "done"
    assert deb.json()["debrief"]["sentiment"] == "tough"
    assert client.post("/api/rounds/9999/debrief", json={"sentiment": "good"}).status_code == 404

    # A prep task for this application picks up the prior debrief automatically.
    task = client.post("/api/agent-tasks", json={"kind": "prep", "applicationId": 1}).json()
    assert task["payload"]["prior_debriefs"][0]["sentiment"] == "tough"

    assert client.delete(f"/api/rounds/{rid}").status_code == 200
    assert client.get("/api/applications/1/rounds").json() == []
