"""JSON library / profile / sources APIs (the React replacements for the Jinja
HTMX pages). Smoke-level: each surface's core round-trip through the same DALs."""

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


def test_library_crud_roundtrip(client: TestClient) -> None:
    assert client.get("/api/library").json() == {
        "experiences": [],
        "projects": [],
        "skills": [],
        "summaries": [],
    }
    exp = client.post("/api/library/experiences", json={"company": "Acme", "role": "Eng"}).json()
    b = client.post(
        "/api/library/bullets", json={"experience_id": exp["id"], "text": "Shipped it."}
    ).json()
    assert b["verified"] is False
    # Tag attach/detach.
    tag = client.post(
        f"/api/library/tags/bullet/{b['id']}", json={"facet": "tech", "value": "python"}
    ).json()
    assert tag["facet"] == "tech"
    assert (
        client.post(
            f"/api/library/tags/bullet/{b['id']}", json={"facet": "bogus", "value": "x"}
        ).status_code
        == 400
    )
    assert client.delete(f"/api/library/tags/bullet/{b['id']}/{tag['id']}").status_code == 200
    # Patch + verify the bullet.
    assert (
        client.patch(f"/api/library/bullets/{b['id']}", json={"facts_verified": True}).json()[
            "verified"
        ]
        is True
    )
    # Skills uniqueness.
    client.post("/api/library/skills", json={"name": "Python"})
    assert client.post("/api/library/skills", json={"name": "Python"}).status_code == 409

    lib = client.get("/api/library").json()
    assert lib["experiences"][0]["bullets"][0]["verified"] is True
    assert {s["name"] for s in lib["skills"]} == {"Python"}

    assert client.delete(f"/api/library/bullets/{b['id']}").status_code == 200


def test_profile_details_roundtrip(client: TestClient) -> None:
    assert client.get("/api/profile/details").json()["fullName"] == ""
    saved = client.post(
        "/api/profile/details",
        json={"full_name": "Dev One", "email": "d@x.com", "links": "github.com/d\nx.com/d"},
    ).json()
    assert saved["fullName"] == "Dev One"
    assert saved["links"] == ["github.com/d", "x.com/d"]
    # Persisted.
    assert client.get("/api/profile/details").json()["email"] == "d@x.com"


def test_sources_add_toggle_delete(client: TestClient) -> None:
    state = client.get("/api/sources").json()
    assert state["sources"] == []
    assert "greenhouse" in state["atsTypes"]
    src = client.post(
        "/api/sources", json={"ats_type": "greenhouse", "slug": "acme", "company": "Acme"}
    ).json()
    assert src["enabled"] == 1
    # Duplicate slug -> 409; unsupported type -> 400.
    assert (
        client.post(
            "/api/sources", json={"ats_type": "greenhouse", "slug": "acme", "company": "Acme"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/sources", json={"ats_type": "nope", "slug": "x", "company": "Y"}
        ).status_code
        == 400
    )
    assert client.post(f"/api/sources/{src['id']}/toggle").json()["enabled"] == 0
    assert (
        client.post("/api/sources/adzuna", json={"app_id": "a", "app_key": "k"}).json()["ok"]
        == "true"
    )
    assert client.delete(f"/api/sources/{src['id']}").status_code == 200
    assert client.get("/api/sources").json()["sources"] == []
