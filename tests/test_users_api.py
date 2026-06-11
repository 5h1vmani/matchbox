"""POST /api/users — the create-profile endpoint behind "Create my profile"."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import matchbox.core.db as db
from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An app whose people/ tree lives under tmp_path, never the real one.

    db_path() and list_profiles() read PROJECT_ROOT at call time, so patching
    the module global redirects every profile DB. MATCHBOX_DB must be unset or
    db_path() would ignore the slug entirely.
    """
    monkeypatch.delenv("MATCHBOX_DB", raising=False)
    monkeypatch.setattr(db, "PROJECT_ROOT", tmp_path)
    with TestClient(create_app()) as c:
        yield c


def test_create_profile_creates_db_and_sets_cookie(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/api/users", json={"name": "Shiva Padakanti"})
    assert r.status_code == 200
    assert r.json() == {"slug": "shiva-padakanti"}
    assert (tmp_path / "people" / "shiva-padakanti" / "matchbox.db").is_file()
    assert r.cookies.get("mb_profile") == "shiva-padakanti"
    # The new profile is discoverable and (via the cookie) active.
    users = {u["slug"]: u["active"] for u in client.get("/api/users").json()}
    assert users.get("shiva-padakanti") is True


def test_create_profile_slugs_messy_input(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/api/users", json={"name": "  Ada Lovelace 2!  "})
    assert r.status_code == 200
    assert r.json() == {"slug": "ada-lovelace-2"}
    assert (tmp_path / "people" / "ada-lovelace-2" / "matchbox.db").is_file()


def test_create_profile_rejects_empty_slug(client: TestClient) -> None:
    assert client.post("/api/users", json={"name": "###"}).status_code == 400
    assert client.post("/api/users", json={"name": "   "}).status_code == 400


def test_create_profile_rejects_underscore_prefix(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/api/users", json={"name": "_shared"}).status_code == 400
    assert not (tmp_path / "people" / "shared").exists()


def test_create_profile_rejects_demo(client: TestClient) -> None:
    assert client.post("/api/users", json={"name": "Demo"}).status_code == 400


def test_create_profile_duplicate_is_409(client: TestClient) -> None:
    assert client.post("/api/users", json={"name": "Twin"}).status_code == 200
    assert client.post("/api/users", json={"name": "twin"}).status_code == 409
