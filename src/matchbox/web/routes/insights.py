"""JSON API for the Insights / Learn module (prefix /api/insights).

READ-ONLY endpoints.  These endpoints NEVER alter any row; they only
report measurement data.  See matchbox/insights/metrics.py for the
pure-function analytics.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from matchbox.insights import metrics
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/insights")


@router.get("")
def get_summary(conn: ConnDep) -> dict[str, Any]:
    """Full insights summary: totals, funnel, calibration, whats-working."""
    return metrics.summary(conn)


@router.get("/funnel")
def get_funnel(conn: ConnDep) -> dict[str, Any]:
    """Funnel counts and conversion rates across the stage ladder."""
    return metrics.funnel(conn)


@router.get("/calibration")
def get_calibration(conn: ConnDep) -> dict[str, Any]:
    """Calibration: predicted band vs. actual interview conversion."""
    return metrics.calibration(conn)


@router.get("/whats-working")
def get_whats_working(conn: ConnDep) -> dict[str, Any]:
    """Interview conversion broken down by source and role family."""
    return metrics.whats_working(conn)


@router.get("/momentum")
def get_momentum(conn: ConnDep, target: int = 5, week_start: str | None = None) -> dict[str, Any]:
    """Real weekly pace + a healthy/push/rest threshold on the applied count."""
    start: date | None = None
    if week_start:
        try:
            start = date.fromisoformat(week_start)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="week_start must be YYYY-MM-DD") from e
    return metrics.momentum(conn, week_start=start, target=target)


@router.get("/rejection-reasons")
def get_rejection_reasons(conn: ConnDep) -> dict[str, int]:
    """Captured close-reason categories (uncaptured reads as 'unknown')."""
    return metrics.rejection_reasons(conn)
