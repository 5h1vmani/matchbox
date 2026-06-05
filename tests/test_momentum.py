"""Momentum coach (real weekly pace + threshold) and rejection learning
(structured close_reason -> deterministic categories, uncaptured = unknown)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.insights import metrics
from matchbox.tracker import service


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = connect(tmp_path / "m.db")
    migrate(c)
    yield c
    c.close()


def _app(conn: sqlite3.Connection, app_id: int, stage: str = "applied") -> None:
    conn.execute(
        "INSERT INTO job (id, company, title, url, jd_text) VALUES (?, ?, 'R', ?, 'jd')",
        (app_id, f"Co{app_id}", f"http://x/{app_id}"),
    )
    conn.execute("INSERT INTO application (id, job_id, stage) VALUES (?, ?, ?)", (app_id, app_id, stage))


def _event(conn: sqlite3.Connection, app_id: int, kind: str, when: date) -> None:
    conn.execute(
        "INSERT INTO app_event (application_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
        (app_id, kind, kind, when.isoformat() + "T12:00:00.000Z"),
    )


def test_momentum_counts_window_and_thresholds(conn: sqlite3.Connection) -> None:
    today = date.today()
    _app(conn, 1)
    # 3 applications this week, 1 last week (outside the window).
    for d in (0, 1, 2):
        _event(conn, 1, "applied", today - timedelta(days=d))
    _event(conn, 1, "applied", today - timedelta(days=20))
    _event(conn, 1, "screen", today - timedelta(days=1))
    _event(conn, 1, "followup", today - timedelta(days=2))

    m = metrics.momentum(conn, target=5)
    assert m["applied"] == 3  # the day-20 one is outside the 7-day window
    assert m["interviews"] == 1
    assert m["followups"] == 1
    assert m["status"] == "healthy"  # ceil(5/2)=3 <= applied < 5

    assert metrics.momentum(conn, target=2)["status"] == "rest"  # 3 >= 2
    assert metrics.momentum(conn, target=10)["status"] == "push"  # 3 < ceil(10/2)=5


def test_rejection_reasons_group_by_with_unknown(conn: sqlite3.Connection) -> None:
    _app(conn, 1, stage="phone")
    _app(conn, 2, stage="phone")
    _app(conn, 3, stage="phone")
    # Two with captured reasons, one closed without one.
    service.log_response(conn, 1, "rejected", "role_filled")
    service.log_response(conn, 2, "rejected", "role_filled")
    service.set_stage(conn, 3, "rejected")  # no reason captured

    reasons = metrics.rejection_reasons(conn)
    assert reasons == {"role_filled": 2, "unknown": 1}


def test_close_reason_normalizes_unknown_vocab_to_other(conn: sqlite3.Connection) -> None:
    _app(conn, 1, stage="phone")
    service.set_stage(conn, 1, "rejected", "they ghosted via a weird channel")
    row = conn.execute("SELECT close_reason FROM application WHERE id = 1").fetchone()
    assert row["close_reason"] == "other"  # non-empty but off-vocab -> other
