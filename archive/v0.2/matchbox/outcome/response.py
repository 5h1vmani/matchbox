"""Outcome response logging — records interview invites, rejections, offers."""

from __future__ import annotations

from datetime import date

from matchbox.core import db
from matchbox.core.schema import VALID_RESPONSE_TYPES


def log_response(
    profile: str,
    job_id: int,
    *,
    response_type: str,
    response_date: str | None = None,
    note: str | None = None,
) -> int:
    """
    Record an outcome response for a job. Updates both responses table and jobs.response_*.

    Returns the response row ID.
    """
    if response_type not in VALID_RESPONSE_TYPES:
        raise ValueError(
            f"Invalid response_type '{response_type}'. Valid: {sorted(VALID_RESPONSE_TYPES)}"
        )
    rdate = response_date or date.today().isoformat()
    response_id = db.log_response(
        profile,
        job_id,
        response_date=rdate,
        response_type=response_type,
        note=note,
    )
    # Mirror in pipeline state
    new_state = {
        "interview": "interview",
        "offer": "offer",
        "rejection": "rejected",
        "ghosted": "responded",
        "other": "responded",
    }.get(response_type, "responded")
    db.update_job_state(profile, job_id, new_state, note=f"response:{response_type}")
    return response_id
