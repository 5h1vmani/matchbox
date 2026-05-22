"""Tests for the /profile editor."""

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
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_profile_form_renders_empty(client: TestClient) -> None:
    r = client.get("/profile")
    assert r.status_code == 200
    assert "Full name" in r.text
    assert "Links" in r.text


def test_profile_save_creates_row(client: TestClient) -> None:
    r = client.post(
        "/profile",
        data={
            "full_name": "Shiva Padakanti",
            "email": "shiva@example.com",
            "headline": "Generalist engineer",
            "links": "https://github.com/shiva\nhttps://example.com",
        },
    )
    assert r.status_code == 200
    assert "Saved" in r.text

    page = client.get("/profile").text
    assert "Shiva Padakanti" in page
    assert "shiva@example.com" in page
    assert "Generalist engineer" in page
    assert "github.com/shiva" in page


def test_profile_save_updates_existing_row(client: TestClient) -> None:
    client.post("/profile", data={"full_name": "First Try"})
    client.post(
        "/profile",
        data={"full_name": "Second Try", "email": "x@y.com"},
    )

    # Only one row, with the updated values.
    import os

    from matchbox.core.db import connect

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    rows = conn.execute("SELECT full_name, email FROM profile").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Second Try"
    assert rows[0]["email"] == "x@y.com"


def test_profile_save_strips_empty_links(client: TestClient) -> None:
    client.post(
        "/profile",
        data={
            "full_name": "X",
            "links": "https://a.com,,\n,\nhttps://b.com",
        },
    )
    import os

    from matchbox.core.db import connect

    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    row = conn.execute("SELECT links_json FROM profile").fetchone()
    conn.close()
    assert json.loads(row["links_json"]) == ["https://a.com", "https://b.com"]


def test_profile_save_requires_full_name(client: TestClient) -> None:
    r = client.post("/profile", data={"email": "no@name.com"})
    # FastAPI's Form validation rejects with 422 when a required field is missing.
    assert r.status_code == 422
