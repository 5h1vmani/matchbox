"""Full-page renders. HTMX partials live in `jobs.py`, `bulk.py`, etc.

Pages: inbox, insights, profile, settings.

Imports are top-level (not lazy inside functions). Lazy imports were used
previously to defer FastAPI app boot, but the modules below are all part of
the core import graph and load anyway on first request — so the indirection
just hid dependencies.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.person import load_person
from matchbox.outcome.analytics import get_funnel, get_tier_cost_summary
from matchbox.outcome.followup import get_followup_candidates
from matchbox.web.deps import ProfileDep, SettingsDep, shell_context
from matchbox.web.render import render
from matchbox.web.routes.jobs import build_inbox_context

router = APIRouter()


@router.get("/p/{profile}/inbox", response_class=HTMLResponse, include_in_schema=False)
async def inbox(request: Request, settings: SettingsDep, profile: ProfileDep) -> HTMLResponse:
    ctx = shell_context(settings, profile, "inbox")
    ctx.update(build_inbox_context(profile, request.query_params))
    return render(request, "pages/inbox.html", ctx)


@router.get("/p/{profile}/insights", response_class=HTMLResponse, include_in_schema=False)
async def insights(request: Request, settings: SettingsDep, profile: ProfileDep) -> HTMLResponse:
    ctx = shell_context(settings, profile, "insights")
    ctx.update(
        funnel=get_funnel(profile),
        tier_costs=get_tier_cost_summary(profile),
        followups=get_followup_candidates(profile),
        scans=db.get_scan_history(profile, limit=10),
    )
    return render(request, "pages/insights.html", ctx)


@router.get("/p/{profile}/profile", response_class=HTMLResponse, include_in_schema=False)
async def profile_page(
    request: Request, settings: SettingsDep, profile: ProfileDep
) -> HTMLResponse:
    person = load_person(profile)
    ctx = shell_context(settings, profile, "profile")
    ctx["person"] = person
    return render(request, "pages/profile.html", ctx)


@router.get("/p/{profile}/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(
    request: Request, settings: SettingsDep, profile: ProfileDep
) -> HTMLResponse:
    import os

    ctx = shell_context(settings, profile, "settings")
    ctx.update(
        api_key_set=bool(os.getenv("ANTHROPIC_API_KEY")),
        cost_threshold=settings.cost_confirm_threshold_usd,
    )
    return render(request, "pages/settings.html", ctx)
