"""Discovery decision effects (integration spec §6 / handoff §D4).

Each decision mutates `job.discovery_decision` (or `skipped_on`) and fires its
side effect, then returns the updated `Role`(s). The SPA store calls these and
reconciles the response. Authoritative: membership is derived from the persisted
decision, never stored as a separate flag.

* tracked   -> create a tracker `application` at stage='saved'; leaves the queue.
* tailoring -> create a run (the manual tailor hand-off) AND a tracked
               application; returns the run id + the "process run X" prompt.
* dismissed -> mark dismissed (never resurfaces; future jobs dedupe against it).
* watch     -> upsert the company into the watchlist.
* skip      -> set skipped_on = today; stays undecided, drops from today's queue.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from matchbox.discovery_api import repo
from matchbox.scoring.runs import JobSelection, create_run

Role = dict[str, Any]

VALID_DECISIONS = ("tracked", "dismissed", "tailoring", "watch", "skip")


def _run_prompt(run_id: str) -> str:
    """The copy-paste hand-off the user pastes into Claude Code (manual run model)."""
    return f"process run {run_id}"


def decide(
    conn: sqlite3.Connection, job_id: int, decision: str, today: date | None = None
) -> dict[str, Any]:
    """Apply one decision. Returns ``{"roles": [Role...], "run": {...}|None}``."""
    today = today or date.today()
    facts = repo.job_facts(conn, job_id)
    if facts is None:
        return {"roles": [], "run": None}

    run_info: dict[str, str] | None = None

    if decision == "tracked":
        repo.create_application(conn, job_id, stage="saved")
        repo.set_decision(conn, job_id, "tracked")

    elif decision == "tailoring":
        run_id, _ = create_run(conn, selections=[JobSelection(job_id, want_cv=True, want_cover=False)])
        repo.create_application(conn, job_id, stage="saved", run_id=run_id)
        repo.set_decision(conn, job_id, "tailoring")
        run_info = {"runId": run_id, "prompt": _run_prompt(run_id)}

    elif decision == "dismissed":
        repo.set_decision(conn, job_id, "dismissed")

    elif decision == "watch":
        repo.upsert_watchlist(conn, facts["company"])
        repo.set_decision(conn, job_id, "watch")

    elif decision == "skip":
        repo.set_skipped(conn, job_id, today.isoformat())

    else:
        raise ValueError(f"unknown decision: {decision!r}")

    role = repo.load_one(conn, job_id)
    return {"roles": [role] if role else [], "run": run_info}


def batch_decide(
    conn: sqlite3.Connection, job_ids: list[int], decision: str, today: date | None = None
) -> dict[str, Any]:
    """Apply one decision to many jobs. Aggregates the updated roles; for
    `tailoring`, the runs are created individually and the prompts collected."""
    roles: list[Role] = []
    runs: list[dict[str, str]] = []
    for job_id in job_ids:
        res = decide(conn, job_id, decision, today=today)
        roles.extend(res["roles"])
        if res.get("run"):
            runs.append(res["run"])
    out: dict[str, Any] = {"roles": roles}
    # For a batch, surface the first run hand-off (the UI shows one toast); the
    # rest are still created and tracked.
    out["run"] = runs[0] if runs else None
    return out
