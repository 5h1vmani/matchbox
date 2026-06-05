"""Truthful salary benchmark drawn from the user's own discovered-job data.

No external API. No fabrication. If there are no matching salary rows the
function returns percentile=None and confidence="none".
"""

from __future__ import annotations

import sqlite3
import statistics
from typing import Any


def benchmark(
    conn: sqlite3.Connection,
    *,
    base: float,
    role_family: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Compare *base* against salary midpoints from the user's own job pool.

    Parameters
    ----------
    conn:
        Active SQLite connection (must have the job table from migration 007).
    base:
        The base salary to benchmark.
    role_family:
        Optional filter — only rows whose `role_family` matches this value.
    currency:
        Optional filter — only rows whose `salary_currency` matches this value.

    Returns
    -------
    dict with keys:
        percentile  int 0..100 or None
        sampleSize  int
        median      float or None
        currency    str or None
        confidence  "none" | "low" | "medium"
    """
    sql = (
        "SELECT salary_min, salary_max, salary_currency "
        "FROM job "
        "WHERE salary_min IS NOT NULL"
    )
    params: list[Any] = []
    if role_family is not None:
        sql += " AND role_family = ?"
        params.append(role_family)
    if currency is not None:
        sql += " AND salary_currency = ?"
        params.append(currency)

    rows = conn.execute(sql, params).fetchall()

    if not rows:
        return {
            "percentile": None,
            "sampleSize": 0,
            "median": None,
            "currency": currency,
            "confidence": "none",
        }

    midpoints: list[float] = []
    for r in rows:
        mn: float | None = r["salary_min"]
        mx: float | None = r["salary_max"]
        if mn is not None and mx is not None:
            midpoints.append((mn + mx) / 2.0)
        elif mn is not None:
            midpoints.append(mn)
        else:
            # salary_max only (shouldn't happen given WHERE salary_min IS NOT NULL
            # but defensive fallback)
            midpoints.append(mx)  # type: ignore[arg-type]

    n = len(midpoints)
    sorted_pts = sorted(midpoints)
    median_val = statistics.median(sorted_pts)

    # Percentile: fraction of midpoints strictly below `base`, scaled 0-100.
    below = sum(1 for m in sorted_pts if m < base)
    percentile = int(round(below / n * 100))

    # Dominant currency (the filter value when given, else mode of rows).
    if currency is not None:
        resolved_currency: str | None = currency
    else:
        currencies = [r["salary_currency"] for r in rows if r["salary_currency"]]
        resolved_currency = max(set(currencies), key=currencies.count) if currencies else None

    confidence: str
    if n == 0:
        confidence = "none"
    elif n < 8:
        confidence = "low"
    else:
        confidence = "medium"

    return {
        "percentile": percentile,
        "sampleSize": n,
        "median": median_val,
        "currency": resolved_currency,
        "confidence": confidence,
    }
