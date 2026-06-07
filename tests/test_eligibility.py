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
    ev = conn.execute(
        "SELECT kind FROM app_event WHERE application_id = ?", (app_id,)
    ).fetchone()
    assert ev["kind"] == "applied"
    conn.close()
