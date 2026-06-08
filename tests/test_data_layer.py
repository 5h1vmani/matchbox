"""Round-trip tests for the M1 data layer.

These cover the contract surface the library UI depends on: experiences,
bullets, projects, skills, summaries, and polymorphic tagging.
"""

from __future__ import annotations

import sqlite3

import pytest

from matchbox.core import library as lib


def test_migration_is_idempotent(tmp_db: sqlite3.Connection) -> None:
    from matchbox.core.migrations import CURRENT_VERSION, migrate

    assert migrate(tmp_db) == CURRENT_VERSION
    assert migrate(tmp_db) == CURRENT_VERSION  # second call is a no-op


def test_connection_usable_across_threads(tmp_db: sqlite3.Connection) -> None:
    """A connection opened on one thread must be usable on another.

    FastAPI runs sync routes + the get_conn dependency in anyio's thread pool,
    which may create the connection on one pool thread and use/close it on
    another. Without check_same_thread=False every other web request 500s with
    sqlite3.ProgrammingError. TestClient reuses one thread, so it never catches
    this -- hence the explicit cross-thread check here.
    """
    import threading

    captured: dict[str, object] = {}

    def use_on_another_thread() -> None:
        try:
            captured["row"] = tmp_db.execute("SELECT 1").fetchone()
        except sqlite3.ProgrammingError as exc:
            captured["error"] = exc

    worker = threading.Thread(target=use_on_another_thread)
    worker.start()
    worker.join()
    assert "error" not in captured, captured["error"]
    assert captured["row"] is not None


def test_bullet_roundtrip(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="Forward Deployed Engineer")
    bullet = lib.add_bullet(
        tmp_db,
        experience_id=exp.id,
        text="Built ETL pipelines processing 30M rows/day.",
        has_metric=True,
    )
    assert bullet.id > 0
    assert bullet.has_metric is True
    assert bullet.facts_verified is False  # default

    fetched = lib.get_bullet(tmp_db, bullet.id)
    assert fetched.text == bullet.text


def test_bullet_update_partial(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="FDE")
    bullet = lib.add_bullet(tmp_db, experience_id=exp.id, text="X")

    updated = lib.update_bullet(tmp_db, bullet.id, facts_verified=True)
    assert updated.facts_verified is True
    assert updated.text == "X"  # untouched


def test_tag_attach_detach_and_query(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="FDE")
    b = lib.add_bullet(tmp_db, experience_id=exp.id, text="Shipped a thing.")

    lib.attach_tag(tmp_db, item_type="bullet", item_id=b.id, facet="tech", value="python")
    tag2 = lib.attach_tag(tmp_db, item_type="bullet", item_id=b.id, facet="tech", value="sql")

    tags = lib.tags_for(tmp_db, item_type="bullet", item_id=b.id)
    assert {t.value for t in tags} == {"python", "sql"}

    # finding the same facet+value returns the same row (no duplicates)
    again = lib.find_or_create_tag(tmp_db, facet="tech", value="sql")
    assert again.id == tag2.id

    items = lib.items_with_tag(tmp_db, tag_id=tag2.id, item_type="bullet")
    assert items == [("bullet", b.id)]

    lib.detach_tag(tmp_db, item_type="bullet", item_id=b.id, tag_id=tag2.id)
    remaining = lib.tags_for(tmp_db, item_type="bullet", item_id=b.id)
    assert {t.value for t in remaining} == {"python"}


def test_delete_bullet_cleans_item_tags(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="FDE")
    b = lib.add_bullet(tmp_db, experience_id=exp.id, text="X")
    lib.attach_tag(tmp_db, item_type="bullet", item_id=b.id, facet="tech", value="rust")

    lib.delete_bullet(tmp_db, b.id)

    assert lib.tags_for(tmp_db, item_type="bullet", item_id=b.id) == []
    with pytest.raises(LookupError):
        lib.get_bullet(tmp_db, b.id)


def test_cascade_delete_experience_removes_bullets(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="FDE")
    lib.add_bullet(tmp_db, experience_id=exp.id, text="X")
    lib.add_bullet(tmp_db, experience_id=exp.id, text="Y")

    tmp_db.execute("DELETE FROM experience WHERE id = ?", (exp.id,))

    assert lib.list_bullets(tmp_db, experience_id=exp.id) == []


def test_project_skill_summary_roundtrip(tmp_db: sqlite3.Connection) -> None:
    p = lib.add_project(tmp_db, name="Matchbox", text="Built a local CV app.", url="https://x")
    s = lib.add_skill(tmp_db, name="Python", category="languages", proficiency="expert")
    sm = lib.add_summary(tmp_db, label="ml-focus", text="ML-leaning generalist engineer.")

    assert lib.get_project(tmp_db, p.id).name == "Matchbox"
    assert lib.get_skill(tmp_db, s.id).proficiency == "expert"
    assert lib.get_summary(tmp_db, sm.id).label == "ml-focus"

    # Skill name is unique case-insensitively
    with pytest.raises(sqlite3.IntegrityError):
        lib.add_skill(tmp_db, name="python")


def test_joined_views_pair_items_with_tags(tmp_db: sqlite3.Connection) -> None:
    exp = lib.add_experience(tmp_db, company="Modal", role="FDE")
    b = lib.add_bullet(tmp_db, experience_id=exp.id, text="X")
    lib.attach_tag(tmp_db, item_type="bullet", item_id=b.id, facet="impact", value="metric")

    view = lib.bullets_with_tags(tmp_db, experience_id=exp.id)
    assert len(view) == 1
    assert view[0].kind == "bullet"
    assert {t.value for t in view[0].tags} == {"metric"}


def test_tag_facet_constraint(tmp_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        lib.find_or_create_tag(tmp_db, facet="bogus", value="x")  # type: ignore[arg-type]


def test_status_enum_constraint(tmp_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        tmp_db.execute(
            "INSERT INTO job (company, title, url, jd_text, status) VALUES (?, ?, ?, ?, ?)",
            ("X", "Y", "https://x/1", "JD", "bogus"),
        )
