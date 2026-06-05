"""Discovery UI backend (matchbox.discovery_api) — the serializer, the
score_breakdown_json -> Role mapping, membership rules, and the decision effects.

Mirrors tests/test_tracker.py. (The name is `_api` to avoid colliding with
tests/test_discovery.py, which covers the unrelated upstream ATS pollers.)
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.discovery_api import repo, rules, service


def _breakdown(band: str, *, elig: dict | None = None, dims: list | None = None) -> str:
    bd: dict = {"total": 0.5, "band": band, "dimensions": dims or []}
    if elig is not None:
        bd["eligibility"] = elig
    return json.dumps(bd)


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "d.db")
    migrate(c)
    # An ATS source for the display label.
    c.execute(
        "INSERT INTO ats_source (id, ats_type, slug, company) "
        "VALUES (1, 'greenhouse', 'acme', 'Acme')"
    )
    # A strong, eligible, scored, open job.
    c.execute(
        "INSERT INTO job (id, source, company, title, location, url, apply_url, jd_text, "
        "posted_at, status, score, score_breakdown_json, remote) "
        "VALUES (1, 1, 'Acme', 'Staff Engineer', 'Remote', 'http://x/1', 'http://x/1/apply', "
        "'Line one.\n\nLine two.', ?, 'scored', 0.83, ?, 1)",
        (
            date.today().isoformat(),
            _breakdown(
                "strong",
                elig={"status": "eligible", "reason": "India-based, no coding gate."},
                dims=[{"name": "semantic_fit", "score": 0.8, "weight": 0.35, "reason": "great match"}],
            ),
        ),
    )
    # An ineligible job -> set-aside.
    c.execute(
        "INSERT INTO job (id, source, company, title, location, url, jd_text, status, "
        "score, score_breakdown_json, remote) "
        "VALUES (2, 1, 'Globex', 'ML Lead', 'Berlin', 'http://x/2', 'jd', 'scored', 0.79, ?, 0)",
        (_breakdown("stretch", elig={"status": "not_eligible", "reason": "EU only."}),),
    )
    # An unscored job -> never enters discovery.
    c.execute(
        "INSERT INTO job (id, source, company, title, location, url, jd_text, status, remote) "
        "VALUES (3, 1, 'Initech', 'Intern', 'Remote', 'http://x/3', 'jd', 'new', 0)"
    )
    yield c
    c.close()


# ── rules: the score_breakdown_json -> Role mapping (the crux) ─────────────────


def test_fit_level_prefers_band_then_score():
    assert rules.fit_level(0.1, "strong") == "strong"
    assert rules.fit_level(0.1, "stretch") == "good"   # band stretch -> design "good"
    assert rules.fit_level(0.1, "weak") == "stretch"
    assert rules.fit_level(0.1, "skip") == "stretch"
    # No band -> numeric thresholds.
    assert rules.fit_level(0.80, None) == "strong"
    assert rules.fit_level(0.70, None) == "good"
    assert rules.fit_level(0.40, None) == "stretch"


def test_eligibility_reconciles_judge_enum():
    def bd(s):
        return {"eligibility": {"status": s, "reason": "r"}}

    assert rules.eligibility(bd("eligible"))["status"] == "eligible"
    assert rules.eligibility(bd("not_eligible"))["status"] == "ineligible"
    assert rules.eligibility(bd("stretch"))["status"] == "unclear"
    # Absent judge output -> unclear, no invented reason.
    assert rules.eligibility({"band": "strong"}) == {"status": "unclear", "reason": ""}
    assert rules.eligibility(None) == {"status": "unclear", "reason": ""}


def test_fit_reason_is_top_weighted_dimension_verbatim():
    bd = {
        "dimensions": [
            {"name": "a", "score": 0.2, "weight": 0.1, "reason": "weak signal"},
            {"name": "b", "score": 0.9, "weight": 0.4, "reason": "strong signal"},
        ]
    }
    assert rules.fit_reason(bd) == "strong signal"
    assert rules.fit_reason({"dimensions": []}) == ""
    assert rules.fit_reason(None) == ""


def test_freshness_open_default_and_closing_and_closed():
    today = date(2026, 6, 5)
    assert rules.freshness(None, None, today) == ("open", None)
    assert rules.freshness("closed", None, today) == ("closed", None)
    assert rules.freshness(None, "2026-06-10", today) == ("closing", 5)
    assert rules.freshness(None, "2026-06-01", today) == ("closed", None)  # past deadline


# Queue membership / ordering / cap live client-side (byte-identical to the
# design), so there is no Python membership to unit-test here. load_roles' one
# server-side membership rule — excluding roles skipped today — is covered by
# test_skip_* below.


# ── serializer ─────────────────────────────────────────────────────────────────


def test_serialize_shape_and_only_scored_enter(conn):
    roles = repo.load_roles(conn)
    ids = {r["id"] for r in roles}
    assert ids == {"1", "2"}  # job 3 is unscored -> excluded
    r1 = next(r for r in roles if r["id"] == "1")
    assert r1["company"] == "Acme"
    assert r1["title"] == "Staff Engineer"
    assert r1["fit"]["level"] == "strong"
    assert r1["fit"]["reason"] == "great match"
    assert r1["eligibility"]["status"] == "eligible"
    assert r1["remote"] is True
    assert r1["salary"] is None             # not stored on job
    assert r1["coverage"] is None           # no requirement match data
    assert r1["source"] == "Greenhouse"
    assert r1["freshness"] == "open"        # default until verify_open runs
    assert r1["mono"]["bg"].startswith("#")
    assert r1["jd"] == ["Line one."]  # the list trims the JD to the card's pulled line
    assert r1["decision"] is None
    # The drawer fetches the full JD via load_one (no jd_limit).
    full = repo.load_one(conn, 1)
    assert full is not None and full["jd"] == ["Line one.", "Line two."]


def test_ineligible_role_serializes_as_set_aside(conn):
    roles = repo.load_roles(conn)
    r2 = next(r for r in roles if r["id"] == "2")
    assert r2["eligibility"]["status"] == "ineligible"
    # Ineligible + undecided -> the client tucks it into the set-aside group.
    assert r2["decision"] is None


# ── decision effects (handoff §D4) ─────────────────────────────────────────────


def test_track_creates_saved_application_and_leaves_queue(conn):
    res = service.decide(conn, 1, "tracked")
    role = res["roles"][0]
    assert role["decision"] == "tracked"
    app = conn.execute("SELECT stage, status, job_id FROM application WHERE job_id = 1").fetchone()
    assert app is not None
    assert app["stage"] == "saved"
    assert app["status"] == "draft"  # legacy CHECK-valid status backing the stage
    # Decided -> the client drops it from the queue.
    assert role["decision"] == "tracked"


def test_tailoring_creates_run_and_application_and_returns_prompt(conn):
    res = service.decide(conn, 1, "tailoring")
    assert res["run"] is not None
    run_id = res["run"]["runId"]
    assert res["run"]["prompt"] == f"process run {run_id}"
    # A run row + run_job + a tracked application linked to the run exist.
    assert conn.execute("SELECT 1 FROM run WHERE id = ?", (run_id,)).fetchone() is not None
    assert conn.execute("SELECT 1 FROM run_job WHERE run_id = ? AND job_id = 1", (run_id,)).fetchone() is not None
    app = conn.execute("SELECT run_id, stage FROM application WHERE job_id = 1").fetchone()
    assert app["run_id"] == run_id
    assert app["stage"] == "saved"
    assert res["roles"][0]["decision"] == "tailoring"


def test_dismiss_marks_and_dedupes_future_jobs(conn):
    service.decide(conn, 1, "dismissed")
    assert repo.load_one(conn, 1)["decision"] == "dismissed"
    # A new job at the same url (or company+title) is a dismissed duplicate.
    assert repo.is_dismissed_duplicate(conn, url="http://x/1", company="Acme", title="Staff Engineer") is True
    assert repo.is_dismissed_duplicate(conn, url=None, company="Acme", title="Staff Engineer") is True
    assert repo.is_dismissed_duplicate(conn, url="http://other", company="Other", title="Role") is False


def test_watch_upserts_company_into_watchlist(conn):
    service.decide(conn, 1, "watch")
    wl = repo.load_watchlist(conn)
    assert any(w["company"] == "Acme" for w in wl)
    # Idempotent: deciding watch again does not duplicate the row.
    service.decide(conn, 1, "watch")
    rows = conn.execute("SELECT COUNT(*) c FROM watchlist WHERE company = 'Acme'").fetchone()
    assert rows["c"] == 1


def test_skip_sets_skipped_on_today_and_stays_undecided(conn):
    today = date.today()
    res = service.decide(conn, 1, "skip", today=today)
    role = res["roles"][0]
    assert role["decision"] is None  # still undecided
    skipped = conn.execute("SELECT skipped_on FROM job WHERE id = 1").fetchone()["skipped_on"]
    assert skipped == today.isoformat()
    # load_roles drops it from today's list (skipped-today guard); it returns tomorrow.
    tomorrow = today + timedelta(days=1)
    assert all(r["id"] != "1" for r in repo.load_roles(conn, today))
    assert any(r["id"] == "1" for r in repo.load_roles(conn, tomorrow))


def test_batch_decide_aggregates_roles(conn):
    res = service.batch_decide(conn, [1, 2], "dismissed")
    assert {r["id"] for r in res["roles"]} == {"1", "2"}
    assert repo.load_one(conn, 1)["decision"] == "dismissed"
    assert repo.load_one(conn, 2)["decision"] == "dismissed"


def test_open_eligible_count_on_watchlist(conn):
    # Acme has one open, eligible, scored, undecided role (job 1).
    repo.upsert_watchlist(conn, "Acme")
    wl = repo.load_watchlist(conn)
    acme = next(w for w in wl if w["company"] == "Acme")
    assert acme["openRoles"] == 1
    # Once tracked, it is decided and no longer counts as open.
    service.decide(conn, 1, "tracked")
    acme = next(w for w in repo.load_watchlist(conn) if w["company"] == "Acme")
    assert acme["openRoles"] == 0
