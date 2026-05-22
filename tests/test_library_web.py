"""End-to-end web tests for the library screen.

These exercise the full request stack — FastAPI route → library helpers →
SQLite → Jinja fragment — using a per-test temp DB selected via the
`MATCHBOX_DB` env var.
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
    # Re-import is unnecessary because each request opens a new connection
    # via get_conn(), and connect() reads MATCHBOX_DB fresh each time.
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_index_page_renders(client: TestClient) -> None:
    r = client.get("/library")
    assert r.status_code == 200
    assert "Library" in r.text
    assert "Add experience" in r.text


def test_root_redirects_to_onboarding_when_empty(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/onboarding"


def test_root_redirects_to_library_when_profile_exists(client: TestClient) -> None:
    # Once any experience exists, the root sends the user to the library.
    client.post("/library/experiences", data={"company": "Modal", "role": "FDE"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/library"


def test_create_experience_then_bullet(client: TestClient) -> None:
    r = client.post(
        "/library/experiences",
        data={"company": "Modal", "role": "Forward Deployed Engineer"},
    )
    assert r.status_code == 200
    assert "Modal" in r.text
    assert "Forward Deployed Engineer" in r.text

    # Pull the experience id out of the rendered fragment.
    # The block is `<article id="experience-{id}" ...>`.
    import re

    m = re.search(r'experience-(\d+)"', r.text)
    assert m is not None, r.text
    exp_id = int(m.group(1))

    r2 = client.post(
        "/library/bullets",
        data={"experience_id": str(exp_id), "text": "Shipped X.", "has_metric": "on"},
    )
    assert r2.status_code == 200
    assert "Shipped X." in r2.text
    assert "metric" in r2.text

    r3 = client.get("/library")
    assert "Modal" in r3.text
    assert "Shipped X." in r3.text


def test_library_index_renders_tag_autocomplete_datalist(client: TestClient) -> None:
    """Once any tag exists, the datalist surfaces it for the autocomplete."""
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post("/library/bullets", data={"experience_id": str(exp_id), "text": "X"})
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]
    client.post(f"/library/tags/bullet/{bullet_id}", data={"facet": "tech", "value": "python"})

    page = client.get("/library").text
    assert '<datalist id="tags-all">' in page
    assert '<option value="python">tech</option>' in page
    # The bullet's add-tag input references the list.
    assert 'list="tags-all"' in page


def test_tag_attach_and_detach(client: TestClient) -> None:
    exp = client.post("/library/experiences", data={"company": "Modal", "role": "FDE"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]

    bullet = client.post(
        "/library/bullets",
        data={"experience_id": str(exp_id), "text": "X."},
    )
    bullet_id = int(re.search(r'bullet-(\d+)"', bullet.text).group(1))  # type: ignore[union-attr]

    r = client.post(
        f"/library/tags/bullet/{bullet_id}",
        data={"facet": "tech", "value": "python"},
    )
    assert r.status_code == 200
    assert "tech:" in r.text
    assert "python" in r.text

    tag_id = int(re.search(rf'tag-bullet-{bullet_id}-(\d+)"', r.text).group(1))  # type: ignore[union-attr]

    r2 = client.delete(f"/library/tags/bullet/{bullet_id}/{tag_id}")
    assert r2.status_code == 200

    # Page no longer shows the chip
    full = client.get("/library").text
    assert f"tag-bullet-{bullet_id}-{tag_id}" not in full


def test_edit_form_then_save(client: TestClient) -> None:
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post("/library/bullets", data={"experience_id": str(exp_id), "text": "old text"})
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]

    # GET edit form
    form = client.get(f"/library/bullets/{bullet_id}/edit")
    assert form.status_code == 200
    assert "old text" in form.text
    assert "Save" in form.text and "Cancel" in form.text

    # PATCH with new text and toggles checked
    save = client.patch(
        f"/library/bullets/{bullet_id}",
        data={"text": "new text", "has_metric": "on", "facts_verified": "on"},
    )
    assert save.status_code == 200
    assert "new text" in save.text
    assert "metric" in save.text
    assert ">verified<" in save.text


def test_edit_form_unchecks_clear_flags(client: TestClient) -> None:
    """The full-edit PATCH treats missing checkboxes as false. Editing a
    verified bullet with the checkboxes unchecked clears those flags."""
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post(
        "/library/bullets",
        data={"experience_id": str(exp_id), "text": "x", "has_metric": "on"},
    )
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]

    save = client.patch(
        f"/library/bullets/{bullet_id}",
        data={"text": "still x"},  # no checkboxes → both false
    )
    assert save.status_code == 200
    assert ">unverified<" in save.text
    assert ">metric<" not in save.text


def test_edit_cancel_returns_read_only_row(client: TestClient) -> None:
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post("/library/bullets", data={"experience_id": str(exp_id), "text": "stable"})
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]

    row = client.get(f"/library/bullets/{bullet_id}/row")
    assert row.status_code == 200
    assert "stable" in row.text
    assert "<textarea" not in row.text


def test_delete_bullet(client: TestClient) -> None:
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post("/library/bullets", data={"experience_id": str(exp_id), "text": "to delete"})
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]

    r = client.delete(f"/library/bullets/{bullet_id}")
    assert r.status_code == 200
    assert "to delete" not in client.get("/library").text


def test_skill_duplicate_returns_409(client: TestClient) -> None:
    client.post("/library/skills", data={"name": "Python"})
    r = client.post("/library/skills", data={"name": "python"})
    assert r.status_code == 409


def test_invalid_facet_rejected(client: TestClient) -> None:
    exp = client.post("/library/experiences", data={"company": "X", "role": "Y"})
    import re

    exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
    b = client.post("/library/bullets", data={"experience_id": str(exp_id), "text": "X"})
    bullet_id = int(re.search(r'bullet-(\d+)"', b.text).group(1))  # type: ignore[union-attr]

    r = client.post(
        f"/library/tags/bullet/{bullet_id}",
        data={"facet": "bogus", "value": "x"},
    )
    assert r.status_code == 400


def test_persistence_across_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bullet survives shutting down and restarting the app."""
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))

    with TestClient(create_app()) as c:
        exp = c.post("/library/experiences", data={"company": "Modal", "role": "FDE"})
        import re

        exp_id = int(re.search(r'experience-(\d+)"', exp.text).group(1))  # type: ignore[union-attr]
        c.post(
            "/library/bullets",
            data={"experience_id": str(exp_id), "text": "Persisted bullet."},
        )

    with TestClient(create_app()) as c2:
        page = c2.get("/library").text
        assert "Persisted bullet." in page
