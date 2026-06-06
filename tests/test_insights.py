"""Tests for the Insights / Learn module (metrics.py).

Seed pattern follows tests/test_agent_tasks.py:
    conn = connect(tmp_path / "x.db"); migrate(conn)

Scenario:
    job1 (role_family='backend')  -- 3 applications
    job2 (role_family='frontend') -- 2 applications

    app1: source='linkedin', stage='phone',    predicted_band='strong'
          events: applied, screen
    app2: source='linkedin', stage='saved',    predicted_band='weak'
          events: (none beyond saved)
    app3: source='referral', stage='onsite',   predicted_band='strong'
          events: applied, onsite
    app4: source='referral', stage='offer',    predicted_band='stretch'
          events: applied, onsite, offer
    app5: source='linkedin', stage='rejected', predicted_band='weak'
          events: applied (then rejected — terminal, not on ladder)

Expected funnel counts (apps that EVER reached each stage):
    saved:    5  (all apps reach at minimum "saved")
    applied:  4  (app2 never applied)
    phone:    3  (app1 via stage+screen, app3 via onsite implies phone, app4 via offer implies phone)
    onsite:   2  (app3, app4)
    offer:    1  (app4)
    accepted: 0

Calibration:
    strong  -> 2 total, 2 interviews (app1 phone, app3 onsite)  rate=1.0
    weak    -> 2 total, 0 interviews                            rate=0.0
    stretch -> 1 total, 1 interview  (app4 offer)               rate=1.0

whats_working:
    bySource:
        linkedin: 3 total, 1 interview (app1), rate=0.333...
        referral: 2 total, 2 interviews (app3, app4), rate=1.0
    byRoleFamily:
        backend:  3 total (job1), 2 interviews (app1, app3? -- depends on assignment)

NOTE: app1,app2,app3 -> job1=backend  |  app4,app5 -> job2=frontend
    backend:  3 total, 2 interviews (app1 phone + app3 onsite), rate=0.666...
    frontend: 2 total, 1 interview  (app4 offer), rate=0.5
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.insights.metrics import (
    STAGE_LADDER,
    calibration,
    funnel,
    reached_stage_for,
    summary,
    whats_working,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "insights_test.db")
    migrate(conn)
    return conn


def _insert_job(
    conn: sqlite3.Connection,
    company: str = "Acme",
    title: str = "Engineer",
    role_family: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, role_family) VALUES (?,?,?,?,?)",
        (company, title, f"https://example.com/{company}/{title}", "JD text", role_family),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_app(
    conn: sqlite3.Connection,
    job_id: int,
    stage: str,
    source: str | None = None,
    predicted_band: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO application (job_id, stage, source, predicted_band) VALUES (?,?,?,?)",
        (job_id, stage, source, predicted_band),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_event(conn: sqlite3.Connection, app_id: int, kind: str) -> None:
    conn.execute(
        "INSERT INTO app_event (application_id, kind, text) VALUES (?,?,?)",
        (app_id, kind, kind),
    )
    conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    """Seed the scenario described in the module docstring."""
    job1 = _insert_job(conn, "Alpha", "Backend Dev", role_family="backend")
    job2 = _insert_job(conn, "Beta", "Frontend Dev", role_family="frontend")

    # app1: linkedin, stage=phone, strong — events: applied, screen
    app1 = _insert_app(conn, job1, "phone", source="linkedin", predicted_band="strong")
    _insert_event(conn, app1, "applied")
    _insert_event(conn, app1, "screen")

    # app2: linkedin, stage=saved, weak — no events beyond saved
    _insert_app(conn, job1, "saved", source="linkedin", predicted_band="weak")

    # app3: referral, stage=onsite, strong — events: applied, onsite
    app3 = _insert_app(conn, job1, "onsite", source="referral", predicted_band="strong")
    _insert_event(conn, app3, "applied")
    _insert_event(conn, app3, "onsite")

    # app4: referral, stage=offer, stretch — events: applied, onsite, offer
    app4 = _insert_app(conn, job2, "offer", source="referral", predicted_band="stretch")
    _insert_event(conn, app4, "applied")
    _insert_event(conn, app4, "onsite")
    _insert_event(conn, app4, "offer")

    # app5: linkedin, stage=rejected, weak — events: applied (terminal)
    app5 = _insert_app(conn, job2, "rejected", source="linkedin", predicted_band="weak")
    _insert_event(conn, app5, "applied")


# ── empty DB ──────────────────────────────────────────────────────────────────


def test_empty_db_reached_stage(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert reached_stage_for(conn) == {}


def test_empty_db_funnel(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    result = funnel(conn)
    for stage in STAGE_LADDER:
        assert result["counts"][stage] == 0
    for v in result["conversion"].values():
        assert v == 0.0


def test_empty_db_calibration(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert calibration(conn) == {}


def test_empty_db_whats_working(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    result = whats_working(conn)
    assert result == {"bySource": {}, "byRoleFamily": {}}


def test_empty_db_summary(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    result = summary(conn)
    totals = result["totals"]
    assert totals["applications"] == 0
    assert totals["interviews"] == 0
    assert totals["offers"] == 0
    assert totals["accepted"] == 0


# ── funnel ────────────────────────────────────────────────────────────────────


def test_funnel_counts_monotone(tmp_path: Path) -> None:
    """Counts must be non-increasing down the ladder."""
    conn = _db(tmp_path)
    _seed(conn)
    result = funnel(conn)
    counts = result["counts"]
    for i in range(len(STAGE_LADDER) - 1):
        assert counts[STAGE_LADDER[i]] >= counts[STAGE_LADDER[i + 1]], (
            f"counts[{STAGE_LADDER[i]}]={counts[STAGE_LADDER[i]]} < "
            f"counts[{STAGE_LADDER[i+1]}]={counts[STAGE_LADDER[i+1]]}"
        )


def test_funnel_counts_scenario(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    c = funnel(conn)["counts"]
    assert c["saved"] == 5
    assert c["applied"] == 4
    assert c["phone"] == 3
    assert c["onsite"] == 2
    assert c["offer"] == 1
    assert c["accepted"] == 0


def test_funnel_conversion_keys(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    conv = funnel(conn)["conversion"]
    expected_keys = {
        "saved_to_applied",
        "applied_to_phone",
        "phone_to_onsite",
        "onsite_to_offer",
        "offer_to_accepted",
    }
    assert set(conv.keys()) == expected_keys


def test_funnel_conversion_values(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    conv = funnel(conn)["conversion"]
    # saved(5) -> applied(4)  = 0.8
    assert abs(conv["saved_to_applied"] - 0.8) < 0.01
    # applied(4) -> phone(3)  = 0.75
    assert abs(conv["applied_to_phone"] - 0.75) < 0.01
    # phone(3) -> onsite(2)   = 0.666...
    assert abs(conv["phone_to_onsite"] - 2 / 3) < 0.01
    # onsite(2) -> offer(1)   = 0.5
    assert abs(conv["onsite_to_offer"] - 0.5) < 0.01
    # offer(1) -> accepted(0) = 0.0
    assert conv["offer_to_accepted"] == 0.0


# ── calibration ───────────────────────────────────────────────────────────────


def test_calibration_bands_present(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    cal = calibration(conn)
    assert set(cal.keys()) == {"strong", "weak", "stretch"}


def test_calibration_strong(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    strong = calibration(conn)["strong"]
    assert strong["total"] == 2
    assert strong["interviews"] == 2
    assert strong["rate"] == 1.0


def test_calibration_weak(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    weak = calibration(conn)["weak"]
    assert weak["total"] == 2
    assert weak["interviews"] == 0
    assert weak["rate"] == 0.0


def test_calibration_stretch(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    stretch = calibration(conn)["stretch"]
    assert stretch["total"] == 1
    assert stretch["interviews"] == 1
    assert stretch["rate"] == 1.0


# ── whats_working ─────────────────────────────────────────────────────────────


def test_whats_working_by_source(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    by_source = whats_working(conn)["bySource"]
    assert set(by_source.keys()) == {"linkedin", "referral"}

    li = by_source["linkedin"]
    assert li["total"] == 3
    assert li["interviews"] == 1   # only app1 (phone)
    assert abs(li["rate"] - 1 / 3) < 0.01

    ref = by_source["referral"]
    assert ref["total"] == 2
    assert ref["interviews"] == 2  # app3 (onsite) + app4 (offer)
    assert ref["rate"] == 1.0


def test_whats_working_by_role_family(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    by_rf = whats_working(conn)["byRoleFamily"]
    assert set(by_rf.keys()) == {"backend", "frontend"}

    be = by_rf["backend"]
    assert be["total"] == 3          # app1, app2, app3 all on job1=backend
    assert be["interviews"] == 2     # app1 phone + app3 onsite
    assert abs(be["rate"] - 2 / 3) < 0.01

    fe = by_rf["frontend"]
    assert fe["total"] == 2          # app4, app5 on job2=frontend
    assert fe["interviews"] == 1     # app4 offer
    assert fe["rate"] == 0.5


# ── summary ───────────────────────────────────────────────────────────────────


def test_summary_totals(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    totals = summary(conn)["totals"]
    assert totals["applications"] == 5
    assert totals["interviews"] == 3   # phone+
    assert totals["offers"] == 1
    assert totals["accepted"] == 0


def test_summary_has_all_keys(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _seed(conn)
    result = summary(conn)
    assert set(result.keys()) == {
        "totals",
        "funnel",
        "calibration",
        "whatsWorking",
        "rejectionReasons",
    }
