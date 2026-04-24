"""Follow-up reminders — surfaces jobs that need a nudge."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from matchbox.core import db


def get_followup_candidates(
    profile: str,
    days_since_applied: int = 10,
    days_since_response: int = 7,
) -> list[dict[str, Any]]:
    """
    Return jobs that may need a follow-up action:
    - Applied N+ days ago with no response
    - Responded N+ days ago with no next step logged

    Returns list of job dicts enriched with 'followup_reason'.
    """
    today = date.today()
    cutoff_applied = (today - timedelta(days=days_since_applied)).isoformat()
    cutoff_responded = (today - timedelta(days=days_since_response)).isoformat()

    candidates: list[dict[str, Any]] = []

    # Applied but no response yet
    applied_jobs = db.list_jobs(profile, state="applied")
    for job in applied_jobs:
        applied = job.applied_date or ""
        if applied and applied <= cutoff_applied:
            row = job.model_dump()
            row["followup_reason"] = f"Applied {applied}, no response after {days_since_applied}d"
            candidates.append(row)

    # Responded (company replied) but no interview scheduled
    responded_jobs = db.list_jobs(profile, state="responded")
    for job in responded_jobs:
        resp_date = job.response_date or ""
        if resp_date and resp_date <= cutoff_responded:
            row = job.model_dump()
            row["followup_reason"] = f"Responded {resp_date}, no interview after {days_since_response}d"
            candidates.append(row)

    return candidates
