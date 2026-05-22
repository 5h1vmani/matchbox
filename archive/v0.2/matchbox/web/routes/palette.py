"""Cmd+K command palette — fuzzy search across pages, profiles, and jobs.

GET /p/{profile}/palette?q=foo  -> ranked HTML results for the modal.

Three result kinds, in this priority order:
  1. Page navigation (Inbox, Insights, Profile, Settings)
  2. Profile switcher (other people/ profiles)
  3. Top jobs in the current profile by score (filtered by query)

Results are ranked by simple substring match — fuzzy is overkill for this scale.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.web.deps import ProfileDep, SettingsDep, list_profiles
from matchbox.web.render import render

router = APIRouter()


_PAGES = [
    ("Inbox", "inbox", "Daily triage table"),
    ("Insights", "insights", "Funnel, cost, follow-ups"),
    ("Profile", "profile", "Scoring weights"),
    ("Settings", "settings", "API key, demo seed"),
]


def _score_match(haystack: str, needle: str) -> int:
    """Tiny ranker: 100 for prefix match, 50 for word-boundary, 10 for any."""
    if not needle:
        return 1
    h = haystack.lower()
    n = needle.lower()
    if h.startswith(n):
        return 100
    if f" {n}" in h or h.startswith(n):
        return 50
    if n in h:
        return 10
    return 0


@router.get("", response_class=HTMLResponse)
async def palette(
    request: Request,
    profile: ProfileDep,
    settings: SettingsDep,
    q: Annotated[str, Query()] = "",
) -> HTMLResponse:
    items: list[dict[str, Any]] = []

    # 1. Pages
    for label, slug, hint in _PAGES:
        s = _score_match(label, q)
        if s > 0:
            items.append(
                {
                    "kind": "page",
                    "label": label,
                    "hint": hint,
                    "url": f"/p/{profile}/{slug}",
                    "score": s,
                }
            )

    # 2. Profile switcher
    for p in list_profiles(settings):
        if p == profile:
            continue
        s = _score_match(p, q)
        if s > 0 or not q:
            items.append(
                {
                    "kind": "profile",
                    "label": f"Switch to {p}",
                    "hint": "profile",
                    "url": f"/p/{p}/inbox",
                    "score": s or 5,
                }
            )

    # 3. Jobs (top 50 by score, filtered by company/role match)
    if q:
        for j in db.list_jobs(profile, role_search=q, limit=10):
            label = f"{j.company} — {j.role}"
            items.append(
                {
                    "kind": "job",
                    "label": label,
                    "hint": f"{j.state} · score {j.total_score or 0:.1f}",
                    "url": f"/p/{profile}/inbox#row-{j.id}",
                    "extra_url": f"/p/{profile}/jobs/{j.id}/detail",
                    "job_id": j.id,
                    "score": _score_match(label, q) or 5,
                }
            )

    items.sort(key=lambda x: -int(x["score"]))
    return render(
        request,
        "components/_palette_results.html",
        {"items": items[:15], "active_profile": profile, "q": q},
    )
