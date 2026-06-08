"""Phase 2: the deterministic eligibility pre-filter (no LLM, every scored job).

It can prove INELIGIBLE from a hard conflict, but never asserts 'eligible' --
absence of a conflict stays 'unclear' (only the judge asserts eligibility).
"""

from __future__ import annotations

from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.discovery_api import repo, rules


def _seed(conn, **job_cols: object) -> int:  # noqa: ANN001 - test helper
    cols = {
        "company": "Acme",
        "title": "Engineer",
        "url": "https://j/1",
        "jd_text": "jd",
        "score": 0.8,
        "score_breakdown_json": '{"band": "strong"}',
        **job_cols,
    }
    keys = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO job ({keys}) VALUES ({marks})", tuple(cols.values()))
    return int(conn.execute("SELECT id FROM job ORDER BY id DESC LIMIT 1").fetchone()[0])


def _set_work_auth(conn, value: str) -> None:  # noqa: ANN001
    conn.execute("DELETE FROM target")
    conn.execute("INSERT INTO target (work_auth_json) VALUES (?)", (value,))


def test_no_sponsorship_blocks_when_user_needs_it(tmp_path: Path) -> None:
    conn = connect(tmp_path / "e.db")
    migrate(conn)
    jid = _seed(conn, sponsorship="none")
    _set_work_auth(conn, '{"needs_sponsorship": true}')
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["eligibility"]["status"] == "ineligible"
    conn.close()


def test_no_block_when_user_does_not_need_sponsorship(tmp_path: Path) -> None:
    conn = connect(tmp_path / "e.db")
    migrate(conn)
    jid = _seed(conn, sponsorship="none")
    _set_work_auth(conn, '{"needs_sponsorship": false}')
    role = repo.load_one(conn, jid)
    assert role is not None
    # No conflict -> defer to the judge; absent judge -> unclear (never fabricated eligible).
    assert role["eligibility"]["status"] == "unclear"
    conn.close()


def test_clearance_blocks_without_clearance(tmp_path: Path) -> None:
    conn = connect(tmp_path / "e.db")
    migrate(conn)
    jid = _seed(conn, clearance_required=1, url="https://j/2")
    _set_work_auth(conn, "{}")
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["eligibility"]["status"] == "ineligible"
    conn.close()


def test_deterministic_ineligible_unit() -> None:
    assert rules.deterministic_ineligible(
        sponsorship="none",
        citizenship_required=None,
        clearance_required=None,
        work_auth={"needs_sponsorship": True},
    ) == {"status": "ineligible", "reason": "No visa sponsorship, which you need."}
    # No explicit conflict -> None (do not rule out).
    assert (
        rules.deterministic_ineligible(
            sponsorship="unknown",
            citizenship_required=None,
            clearance_required=None,
            work_auth={"needs_sponsorship": True},
        )
        is None
    )


# ── geo: the deterministic India filter (rules.india_eligible) ───────────────────


def test_india_eligible_country_code() -> None:
    assert rules.india_eligible(country="in", location=None, remote_scope=None, jd_text=None)
    assert rules.india_eligible(country="India", location=None, remote_scope=None, jd_text=None)
    assert rules.india_eligible(country=" IND ", location=None, remote_scope=None, jd_text=None)


def test_india_eligible_word_in_location() -> None:
    assert rules.india_eligible(
        country=None, location="Bengaluru, India", remote_scope=None, jd_text=None
    )
    assert rules.india_eligible(
        country=None, location="Remote - India", remote_scope=None, jd_text=None
    )


def test_india_eligible_major_city_without_country_word() -> None:
    # Decision Q1: curated metros count even when "India" is never written.
    for city in ("Bengaluru", "Mumbai", "Hyderabad", "Gurugram", "Pune"):
        assert rules.india_eligible(country=None, location=city, remote_scope=None, jd_text=None), (
            city
        )


def test_india_eligible_remote_scope_or_jd_mentions_india() -> None:
    assert rules.india_eligible(country=None, location="Remote", remote_scope="india", jd_text=None)
    assert rules.india_eligible(
        country=None,
        location="Remote",
        remote_scope=None,
        jd_text="Fully remote. Open to candidates based in India.",
    )


def test_not_india_eligible_foreign_role() -> None:
    assert not rules.india_eligible(
        country="us", location="New York", remote_scope=None, jd_text="Onsite in NYC."
    )


def test_not_india_eligible_bare_worldwide_remote() -> None:
    # Decision Q2: a global/worldwide remote that never names India does NOT pass.
    assert not rules.india_eligible(
        country=None,
        location="Remote",
        remote_scope=None,
        jd_text="Work from anywhere in the world.",
    )
    assert not rules.india_eligible(
        country=None, location="Worldwide", remote_scope=None, jd_text=None
    )


def test_indiana_is_not_india() -> None:
    # Word-boundary guard: 'Indiana'/'Indianapolis' must never match 'India'.
    assert not rules.india_eligible(
        country="us", location="Indianapolis, Indiana", remote_scope=None, jd_text=None
    )


def test_india_city_in_jd_body_does_not_pull_in_a_foreign_role() -> None:
    # An explicit foreign country blocks the JD-body city match, so a US role that
    # only name-drops a Bangalore office stays out.
    assert not rules.india_eligible(
        country="us",
        location="San Francisco",
        remote_scope=None,
        jd_text="You'll partner daily with our Bangalore engineering team.",
    )


def test_india_city_in_jd_counts_when_country_unknown() -> None:
    # Real case (a hand-added Deloitte USI role): the city is only in the JD body
    # and there is no country -> India-eligible. The old "JD never counts" rule
    # wrongly hid these.
    jd = "Finance role. Location: Bengaluru/Hyderabad/Pune/Chennai. Qualifications: ..."
    assert rules.india_eligible(country=None, location=None, remote_scope=None, jd_text=jd)


def test_india_word_matches_indian_but_not_indiana() -> None:
    assert rules.india_eligible(
        country=None, location=None, remote_scope=None, jd_text="Open to Indian nationals."
    )
    assert not rules.india_eligible(
        country="us", location="Indianapolis, Indiana", remote_scope=None, jd_text=None
    )


def test_serialize_exposes_india_eligible_true(tmp_path: Path) -> None:
    conn = connect(tmp_path / "g.db")
    migrate(conn)
    jid = _seed(conn, url="https://j/in", location="Bengaluru, India", country="in")
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["indiaEligible"] is True
    conn.close()


def test_serialize_marks_foreign_role_not_india_eligible(tmp_path: Path) -> None:
    conn = connect(tmp_path / "g.db")
    migrate(conn)
    jid = _seed(conn, url="https://j/us", location="New York", country="us", jd_text="Onsite NYC.")
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["indiaEligible"] is False
    conn.close()


def test_serialize_flags_hand_added_role_as_manual(tmp_path: Path) -> None:
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    # add_job sets neither source nor posted_at -> a hand-added role.
    jid = _seed(conn, url="https://j/byhand")
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["manual"] is True
    conn.close()


def test_serialize_scanned_role_is_not_manual(tmp_path: Path) -> None:
    conn = connect(tmp_path / "m.db")
    migrate(conn)
    # The scanners always stamp a posting date; that marks a role as discovered.
    jid = _seed(conn, url="https://j/scanned", posted_at="2026-06-01T00:00:00Z")
    role = repo.load_one(conn, jid)
    assert role is not None
    assert role["manual"] is False
    conn.close()


def test_snapshot_predicted_fit_on_application(tmp_path: Path) -> None:
    """create_application records the predicted band/score for later calibration."""
    conn = connect(tmp_path / "e.db")
    migrate(conn)
    jid = _seed(conn, score=0.83, score_breakdown_json='{"band": "strong"}')
    app_id = repo.create_application(conn, jid, stage="saved")
    row = conn.execute(
        "SELECT predicted_band, predicted_score, applied_at, next_action FROM application WHERE id = ?",
        (app_id,),
    ).fetchone()
    assert row["predicted_band"] == "strong"
    assert row["predicted_score"] == 0.83
    # Saved (not applied): no applied_at, no follow-up reminder yet.
    assert row["applied_at"] is None
    assert row["next_action"] is None
    conn.close()


def test_create_application_at_applied_stamps_followup_reminder(tmp_path: Path) -> None:
    """The Apply-packet submit creates at `applied` with applied_at + a +7d
    follow-up reminder (a due-date computed on read, not a scheduled task)."""
    from datetime import date, timedelta

    conn = connect(tmp_path / "e.db")
    migrate(conn)
    jid = _seed(conn, score=0.7, score_breakdown_json='{"band": "stretch"}')
    app_id = repo.create_application(conn, jid, stage="applied")
    row = conn.execute(
        "SELECT stage, applied_at, next_action, next_action_kind, next_action_at "
        "FROM application WHERE id = ?",
        (app_id,),
    ).fetchone()
    assert row["stage"] == "applied"
    assert row["applied_at"] == date.today().isoformat()
    assert row["next_action_kind"] == "followup"
    assert row["next_action_at"] == (date.today() + timedelta(days=7)).isoformat()
    ev = conn.execute("SELECT kind FROM app_event WHERE application_id = ?", (app_id,)).fetchone()
    assert ev["kind"] == "applied"
    conn.close()
