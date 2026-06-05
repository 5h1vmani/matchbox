"""Pure-function analytics for the Learn / Insights module.

All functions are READ-ONLY.  They NEVER update any row or influence
any ranking.  Every function is null-safe: an empty database returns
zeroed / empty structures without raising.

Stage ladder (ordered, terminal stages excluded):
    saved -> applied -> phone -> onsite -> offer -> accepted
"rejected" is terminal and not part of the ladder.

Event-kind -> ladder-stage mapping used by reached_stage_for():
    applied          -> applied
    reply, screen    -> phone
    onsite           -> onsite
    offer            -> offer
    advanced         -> phone  (generic advancement signal)
"""

from __future__ import annotations

import sqlite3
from typing import Any

# ── ladder ────────────────────────────────────────────────────────────────────

STAGE_LADDER: list[str] = [
    "saved",
    "applied",
    "phone",
    "onsite",
    "offer",
    "accepted",
]

_LADDER_IDX: dict[str, int] = {s: i for i, s in enumerate(STAGE_LADDER)}

# event kind -> the ladder stage it implies (or None to skip)
_EVENT_TO_STAGE: dict[str, str] = {
    "applied": "applied",
    "reply": "phone",
    "screen": "phone",
    "advanced": "phone",
    "onsite": "onsite",
    "offer": "offer",
}


def _ladder_idx(stage: str | None) -> int:
    """Return the position of *stage* in the ladder, or -1 if not in ladder."""
    if stage is None:
        return -1
    return _LADDER_IDX.get(stage, -1)


# ── core helper ──────────────────────────────────────────────────────────────


def reached_stage_for(conn: sqlite3.Connection) -> dict[int, str]:
    """For every application, return the FURTHEST ladder stage it ever reached.

    The "furthest stage" is the maximum of:
      * the application's current ``stage`` column (if it is on the ladder), and
      * any ladder stage implied by its ``app_event`` history.

    "rejected" and "accepted" as a stage value: "accepted" is on the ladder;
    "rejected" is terminal but not on the ladder, so an application whose only
    signal is stage='rejected' will have no ladder entry (excluded from ladder
    counts).  Applications with no ladder signal are omitted from the returned
    dict.
    """
    # Fetch all application ids + their current stage.
    app_rows: list[tuple[int, str | None]] = conn.execute(
        "SELECT id, stage FROM application"
    ).fetchall()

    if not app_rows:
        return {}

    # Build initial map from current stage column.
    best: dict[int, int] = {}  # app_id -> best ladder index so far
    for app_id, stage in app_rows:
        idx = _ladder_idx(stage)
        if idx >= 0:
            best[app_id] = max(best.get(app_id, -1), idx)
        else:
            # Make sure the app_id is present so we can update from events.
            if app_id not in best:
                best[app_id] = -1

    # Update from app_event history.
    event_rows: list[tuple[int, str]] = conn.execute(
        "SELECT application_id, kind FROM app_event"
    ).fetchall()
    for app_id, kind in event_rows:
        stage = _EVENT_TO_STAGE.get(kind)
        if stage is None:
            continue
        idx = _ladder_idx(stage)
        if idx >= 0 and app_id in best:
            best[app_id] = max(best[app_id], idx)

    # Translate back to stage names; drop apps that never reached any rung.
    return {
        app_id: STAGE_LADDER[idx]
        for app_id, idx in best.items()
        if idx >= 0
    }


# ── public analytics functions ────────────────────────────────────────────────


def funnel(conn: sqlite3.Connection) -> dict[str, Any]:
    """Count of applications that EVER reached each ladder stage, plus
    conversion rates between consecutive stages.

    Returns::

        {
            "counts": {"saved": n, "applied": m, ...},
            "conversion": {"saved_to_applied": 0.42, ...},
        }
    """
    stage_map = reached_stage_for(conn)

    counts: dict[str, int] = {s: 0 for s in STAGE_LADDER}
    for furthest in stage_map.values():
        best_idx = _LADDER_IDX[furthest]
        # Every stage at or below the furthest is "reached".
        for i in range(best_idx + 1):
            counts[STAGE_LADDER[i]] += 1

    conversion: dict[str, float] = {}
    for i in range(len(STAGE_LADDER) - 1):
        from_stage = STAGE_LADDER[i]
        to_stage = STAGE_LADDER[i + 1]
        key = f"{from_stage}_to_{to_stage}"
        denom = counts[from_stage]
        conversion[key] = round(counts[to_stage] / denom, 4) if denom else 0.0

    return {"counts": counts, "conversion": conversion}


def calibration(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compare predicted_band to actual conversion (reached >= 'phone').

    Returns a dict keyed by band name, each value::

        {"total": n, "interviews": m, "rate": 0.5}

    Applications with NULL predicted_band are skipped.
    """
    stage_map = reached_stage_for(conn)
    phone_idx = _LADDER_IDX["phone"]

    rows: list[tuple[int, str | None]] = conn.execute(
        "SELECT id, predicted_band FROM application WHERE predicted_band IS NOT NULL"
    ).fetchall()

    totals: dict[str, int] = {}
    interviews: dict[str, int] = {}

    for app_id, band in rows:
        if band is None:
            continue
        totals[band] = totals.get(band, 0) + 1
        # Did this app ever reach phone or beyond?
        furthest = stage_map.get(app_id)
        reached_interview = (
            furthest is not None and _LADDER_IDX.get(furthest, -1) >= phone_idx
        )
        if reached_interview:
            interviews[band] = interviews.get(band, 0) + 1

    result: dict[str, Any] = {}
    for band, total in totals.items():
        n_interviews = interviews.get(band, 0)
        result[band] = {
            "total": total,
            "interviews": n_interviews,
            "rate": round(n_interviews / total, 4) if total else 0.0,
        }
    return result


def whats_working(conn: sqlite3.Connection) -> dict[str, Any]:
    """Break down interview conversion by `source` and by ``job.role_family``.

    Returns::

        {
            "bySource":     {"linkedin": {"total": n, "interviews": m, "rate": r}, ...},
            "byRoleFamily": {"backend":  {"total": n, "interviews": m, "rate": r}, ...},
        }

    Applications whose source / role_family is NULL are grouped under the
    empty-string key ``""``.
    """
    stage_map = reached_stage_for(conn)
    phone_idx = _LADDER_IDX["phone"]

    rows: list[tuple[int, str | None, str | None]] = conn.execute(
        """
        SELECT a.id, a.source, j.role_family
          FROM application a
          JOIN job j ON j.id = a.job_id
        """
    ).fetchall()

    def _tally(
        groups: dict[str, dict[str, int]], key: str, app_id: int
    ) -> None:
        g = groups.setdefault(key, {"total": 0, "interviews": 0})
        g["total"] += 1
        furthest = stage_map.get(app_id)
        if furthest is not None and _LADDER_IDX.get(furthest, -1) >= phone_idx:
            g["interviews"] += 1

    by_source: dict[str, dict[str, int]] = {}
    by_role: dict[str, dict[str, int]] = {}

    for app_id, source, role_family in rows:
        _tally(by_source, source or "", app_id)
        _tally(by_role, role_family or "", app_id)

    def _rates(groups: dict[str, dict[str, int]]) -> dict[str, Any]:
        return {
            k: {
                "total": v["total"],
                "interviews": v["interviews"],
                "rate": round(v["interviews"] / v["total"], 4) if v["total"] else 0.0,
            }
            for k, v in groups.items()
        }

    return {
        "bySource": _rates(by_source),
        "byRoleFamily": _rates(by_role),
    }


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Top-level summary for the Insights dashboard.

    Returns::

        {
            "totals": {
                "applications": n,
                "interviews":   m,
                "offers":       k,
                "accepted":     j,
            },
            "funnel":        funnel(conn),
            "calibration":   calibration(conn),
            "whatsWorking":  whats_working(conn),
        }
    """
    stage_map = reached_stage_for(conn)

    phone_idx = _LADDER_IDX["phone"]
    offer_idx = _LADDER_IDX["offer"]
    accepted_idx = _LADDER_IDX["accepted"]

    total_apps = conn.execute("SELECT COUNT(*) FROM application").fetchone()[0] or 0
    n_interviews = sum(
        1
        for s in stage_map.values()
        if _LADDER_IDX.get(s, -1) >= phone_idx
    )
    n_offers = sum(
        1
        for s in stage_map.values()
        if _LADDER_IDX.get(s, -1) >= offer_idx
    )
    n_accepted = sum(
        1
        for s in stage_map.values()
        if _LADDER_IDX.get(s, -1) >= accepted_idx
    )

    return {
        "totals": {
            "applications": total_apps,
            "interviews": n_interviews,
            "offers": n_offers,
            "accepted": n_accepted,
        },
        "funnel": funnel(conn),
        "calibration": calibration(conn),
        "whatsWorking": whats_working(conn),
    }
