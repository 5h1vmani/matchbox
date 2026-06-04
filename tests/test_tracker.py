"""Tracker backend — rules, serialization, and the action effects."""

from __future__ import annotations

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.tracker import repo, rules, service


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    migrate(c)
    c.execute(
        "INSERT INTO job (id, company, title, location, url, jd_text) "
        "VALUES (1, 'Acme', 'Engineer', 'Remote', 'http://x', 'jd')"
    )
    c.execute(
        "INSERT INTO application (id, job_id, stage, applied_at, updated_at) "
        "VALUES (1, 1, 'applied', '2026-06-01', '2026-06-01')"
    )
    c.execute("INSERT INTO app_event (application_id, kind, text) VALUES (1, 'applied', 'Applied')")
    yield c
    c.close()


def test_default_action_and_flow():
    assert rules.FLOW == ["saved", "applied", "phone", "onsite", "offer"]
    assert rules.default_action_for("applied")[0] == "followup"
    assert rules.default_action_for("saved") is None


def test_is_stale_rule():
    assert rules.is_stale("applied", None, 12) is True
    assert rules.is_stale("applied", 2, 12) is False  # imminent action
    assert rules.is_stale("saved", None, 99) is False  # not an active stage


def test_serialize_shape(conn):
    app = repo.load_one(conn, 1)
    assert app is not None
    assert app["id"] == "1"
    assert app["company"] == "Acme"
    assert app["stage"] == "applied"
    assert app["mono"]["bg"].startswith("#")
    # the seeded history event serializes through
    assert any(e["kind"] == "applied" for e in app["events"])


def test_advance_stage_sets_default_action_and_event(conn):
    app = service.advance_stage(conn, 1)
    assert app["stage"] == "phone"
    assert app["nextAction"]["kind"] == "prep"
    assert app["events"][0]["text"].startswith("Moved to")


def test_remind_then_mark_done_waits(conn):
    app = service.remind(conn, 1, 0)
    assert app["nextAction"]["due"] == 0
    assert app["nextAction"]["kind"] == "followup"
    app = service.mark_done(conn, 1)
    assert app["nextAction"]["kind"] == "wait"  # applied + sent follow-up -> waiting
    assert app["hasDraft"] is False


def test_log_response_reply_advances_applied_to_phone(conn):
    app = service.log_response(conn, 1, "reply")
    assert app["stage"] == "phone"
    assert app["events"][0]["text"].startswith("Heard back")


def test_toggle_star_round_trips(conn):
    assert service.toggle_star(conn, 1)["starred"] is True
    assert service.toggle_star(conn, 1)["starred"] is False
