"""Setup progress JSON API (prefix /api/setup) — the onboarding rail's data.

Seven ordered steps ("Step N of 7"), each computed from state the user has
already created — one cheap EXISTS-style query per step against the active
profile's DB, plus a filesystem peek at inbox/ for step 1. Nothing is stored:
"done" is derived on every read, so it moves forward as the library grows and
backward honestly if rows are deleted. The React Shell renders the rail while
``current < 7`` (see frontend/src/ui/SetupRail.tsx).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter

from matchbox.web.deps import ConnDep
from matchbox.web.routes.onboarding import _staged_files

router = APIRouter(prefix="/api/setup")


def _exists(conn: sqlite3.Connection, sql: str) -> bool:
    return conn.execute(sql).fetchone() is not None


def _flags(conn: sqlite3.Connection) -> list[tuple[str, str, bool, bool]]:
    """(id, label, done, partial) per step, in rail order.

    `partial` marks visible progress short of done — today only step 2
    (some bullets verified, some still awaiting review).
    """
    row = conn.execute("SELECT COALESCE(SUM(facts_verified), 0), COUNT(*) FROM bullet").fetchone()
    verified, total = int(row[0]), int(row[1])
    verify_done = verified >= 1 and verified == total  # all confirmed, none pending
    return [
        ("history", "Add your history", total > 0 or bool(_staged_files()), False),
        ("verify", "Verify your facts", verify_done, verified >= 1 and not verify_done),
        (
            "profile",
            "Your profile",
            _exists(conn, "SELECT 1 FROM profile WHERE trim(full_name) <> '' LIMIT 1"),
            False,
        ),
        ("targets", "Set your targets", _exists(conn, "SELECT 1 FROM target LIMIT 1"), False),
        ("job", "Add a job", _exists(conn, "SELECT 1 FROM job LIMIT 1"), False),
        (
            "tailor",
            "Tailor a CV",
            _exists(conn, "SELECT 1 FROM run LIMIT 1")
            or _exists(conn, "SELECT 1 FROM application WHERE cv_path IS NOT NULL LIMIT 1"),
            False,
        ),
        (
            "apply",
            "Apply",
            # The tracker stamps applied_at when an application reaches the
            # `applied` stage (tracker/service.py); a row already advanced to
            # phone/onsite/offer has necessarily been applied to as well.
            _exists(
                conn,
                "SELECT 1 FROM application WHERE applied_at IS NOT NULL "
                "OR stage IN ('applied', 'phone', 'onsite', 'offer') LIMIT 1",
            ),
            False,
        ),
    ]


@router.get("/state")
def setup_state(conn: ConnDep) -> dict[str, Any]:
    """The rail's view-model: 7 steps + the index of the first not-done one.

    ``current == 7`` means setup is complete (the rail hides itself). "active"
    is true only for the first not-done step — later steps may already be done
    (they complete independently) without changing where the user is pointed.
    """
    flags = _flags(conn)
    current = next((i for i, (_, _, done, _) in enumerate(flags) if not done), len(flags))
    steps = [
        {"id": sid, "label": label, "done": done, "partial": partial, "active": i == current}
        for i, (sid, label, done, partial) in enumerate(flags)
    ]
    return {"steps": steps, "current": current}
