"""Tests for matchbox.artifacts.repo.

Pattern mirrors test_agent_tasks.py:
    conn = connect(tmp_path / "a.db"); migrate(conn)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matchbox.artifacts import repo
from matchbox.core.db import connect
from matchbox.core.migrations import migrate


def _db(tmp_path: Path):  # noqa: ANN202 - test helper
    conn = connect(tmp_path / "a.db")
    migrate(conn)
    return conn


def _seed(conn) -> tuple[int, int]:  # noqa: ANN001
    """Insert a minimal job and application; return (job_id, application_id)."""
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text) VALUES (?, ?, ?, ?)",
        ("Acme Corp", "Software Engineer", "https://acme.example/jobs/1", "Build things."),
    )
    job_id = int(cur.lastrowid)
    cur2 = conn.execute(
        "INSERT INTO application (job_id) VALUES (?)",
        (job_id,),
    )
    application_id = int(cur2.lastrowid)
    return job_id, application_id


def test_create_prep_body_and_list(tmp_path: Path) -> None:
    """A 'prep' artifact with body shows up in list_for_app; has_draft stays 0."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    artifact_id = repo.create(conn, app_id, "prep", body="Prep brief content.")
    assert isinstance(artifact_id, int) and artifact_id > 0

    artifacts = repo.list_for_app(conn, app_id)
    assert len(artifacts) == 1
    a = artifacts[0]
    assert a["id"] == artifact_id
    assert a["applicationId"] == app_id
    assert a["kind"] == "prep"
    assert a["body"] == "Prep brief content."
    assert a["path"] is None
    assert a["status"] == "draft"

    # has_draft must NOT be set for 'prep'
    row = conn.execute("SELECT has_draft FROM application WHERE id = ?", (app_id,)).fetchone()
    assert row["has_draft"] == 0

    conn.close()


def test_create_followup_sets_has_draft(tmp_path: Path) -> None:
    """A 'followup' artifact must set application.has_draft = 1."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    repo.create(conn, app_id, "followup", body="Thanks for the chat.")

    row = conn.execute("SELECT has_draft FROM application WHERE id = ?", (app_id,)).fetchone()
    assert row["has_draft"] == 1

    conn.close()


def test_create_thankyou_sets_has_draft(tmp_path: Path) -> None:
    """A 'thankyou' artifact must also set application.has_draft = 1."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    repo.create(conn, app_id, "thankyou", body="Thank you for your time.")

    row = conn.execute("SELECT has_draft FROM application WHERE id = ?", (app_id,)).fetchone()
    assert row["has_draft"] == 1

    conn.close()


def test_set_status_sent(tmp_path: Path) -> None:
    """set_status('sent') updates the row and returns the updated dict."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    artifact_id = repo.create(conn, app_id, "followup", body="Following up.")
    updated = repo.set_status(conn, artifact_id, "sent")

    assert updated is not None
    assert updated["status"] == "sent"
    assert updated["id"] == artifact_id

    conn.close()


def test_create_invalid_kind_raises(tmp_path: Path) -> None:
    """create() with an invalid kind raises ValueError before touching the DB."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    with pytest.raises(ValueError, match="invalid kind"):
        repo.create(conn, app_id, "bogus", body="oops")

    conn.close()


def test_create_invalid_status_raises(tmp_path: Path) -> None:
    """create() with an invalid status raises ValueError."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    with pytest.raises(ValueError, match="invalid status"):
        repo.create(conn, app_id, "prep", body="text", status="unknown")

    conn.close()


def test_list_for_app_kind_filter(tmp_path: Path) -> None:
    """list_for_app with kind= returns only matching rows, ordered by id."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    repo.create(conn, app_id, "prep", body="Prep.")
    f_id = repo.create(conn, app_id, "followup", body="Follow-up.")

    only_followup = repo.list_for_app(conn, app_id, kind="followup")
    assert len(only_followup) == 1
    assert only_followup[0]["id"] == f_id

    conn.close()


def test_get_returns_none_for_missing(tmp_path: Path) -> None:
    """get() returns None for a non-existent artifact id."""
    conn = _db(tmp_path)
    assert repo.get(conn, 9999) is None
    conn.close()


def test_set_status_returns_none_for_missing(tmp_path: Path) -> None:
    """set_status() returns None for a non-existent artifact id."""
    conn = _db(tmp_path)
    result = repo.set_status(conn, 9999, "sent")
    assert result is None
    conn.close()


def test_create_cv_path_artifact(tmp_path: Path) -> None:
    """A 'cv' artifact with a path stores it correctly and has_draft stays 0."""
    conn = _db(tmp_path)
    _, app_id = _seed(conn)

    artifact_id = repo.create(conn, app_id, "cv", path="/runs/r1/output/1/cv.pdf", status="final")
    a = repo.get(conn, artifact_id)

    assert a is not None
    assert a["kind"] == "cv"
    assert a["path"] == "/runs/r1/output/1/cv.pdf"
    assert a["body"] is None
    assert a["status"] == "final"

    row = conn.execute("SELECT has_draft FROM application WHERE id = ?", (app_id,)).fetchone()
    assert row["has_draft"] == 0

    conn.close()
