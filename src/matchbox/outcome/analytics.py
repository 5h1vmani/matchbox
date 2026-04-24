"""Pipeline analytics — response rates, conversion funnel, cost tracking."""

from __future__ import annotations

from typing import Any

from matchbox.core import db


def get_funnel(profile: str) -> dict[str, Any]:
    """Return conversion funnel from evaluated → applied → response → interview → offer."""
    stats = db.get_stats(profile)
    evaluated = stats.get("count_evaluated", 0)
    applied = stats.get("count_applied", 0)
    responded = (
        stats.get("count_responded", 0)
        + stats.get("count_interview", 0)
        + stats.get("count_offer", 0)
        + stats.get("count_rejected", 0)
    )
    interview = stats.get("count_interview", 0) + stats.get("count_offer", 0)
    offer = stats.get("count_offer", 0)

    def _pct(num: int, denom: int) -> float:
        return round(num / denom * 100, 1) if denom else 0.0

    return {
        "evaluated": evaluated,
        "applied": applied,
        "applied_rate": _pct(applied, evaluated),
        "responded": responded,
        "response_rate": _pct(responded, applied),
        "interview": interview,
        "interview_rate": _pct(interview, responded),
        "offer": offer,
        "offer_rate": _pct(offer, interview),
        "total_cost_usd": stats.get("total_cost_usd", 0.0),
        "avg_score": stats.get("avg_score", 0.0),
        "cost_per_application": (round(stats["total_cost_usd"] / applied, 2) if applied else 0.0),
    }


def get_tier_cost_summary(profile: str) -> dict[str, Any]:
    """Return average cost and count by tailor tier."""
    jobs = db.list_jobs(profile, state=["tailored", "applied", "responded", "interview", "offer"])
    by_tier: dict[str, list[float]] = {}
    for job in jobs:
        tier = job.tier or "unknown"
        cost = job.tailor_cost_usd or 0.0
        by_tier.setdefault(tier, []).append(cost)
    return {
        tier: {
            "count": len(costs),
            "total_usd": round(sum(costs), 4),
            "avg_usd": round(sum(costs) / len(costs), 4) if costs else 0.0,
        }
        for tier, costs in by_tier.items()
    }
