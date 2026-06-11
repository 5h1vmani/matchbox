"""GET /api/review/counts — the cheap ingest-progress poll for Onboarding.

The screen polls it every few seconds while the user runs `ingest my files`
in Claude Code, so bullets landing and verification progress are visible
in-app instead of only in the terminal.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    with TestClient(create_app()) as c:
        yield c


def test_counts_empty_db(client: TestClient) -> None:
    assert client.get("/api/review/counts").json() == {
        "bullets": 0,
        "verified": 0,
        "experiences": 0,
    }


def test_counts_track_ingest_and_verification(client: TestClient) -> None:
    exp = client.post("/api/library/experiences", json={"company": "Acme", "role": "Eng"}).json()
    b1 = client.post(
        "/api/library/bullets",
        json={"experience_id": exp["id"], "text": "Shipped the deploy pipeline"},
    ).json()
    client.post(
        "/api/library/bullets",
        json={"experience_id": exp["id"], "text": "Cut p95 latency 40%", "has_metric": True},
    )
    assert client.get("/api/review/counts").json() == {
        "bullets": 2,
        "verified": 0,
        "experiences": 1,
    }

    client.post(f"/api/review/bullets/{b1['id']}/verify")
    assert client.get("/api/review/counts").json() == {
        "bullets": 2,
        "verified": 1,
        "experiences": 1,
    }
