"""JSON API for the Insights / Learn module (prefix /api/insights).

READ-ONLY endpoints.  These endpoints NEVER alter any row; they only
report measurement data.  See matchbox/insights/metrics.py for the
pure-function analytics.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

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
