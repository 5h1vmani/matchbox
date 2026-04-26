"""System routes — welcome page (cold start), demo seeding, profile bootstrap.

These are the only routes that don't require a valid profile, since they exist
to handle the empty-state and onboarding journey.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from matchbox.web.deps import SettingsDep, shell_context
from matchbox.web.render import render

router = APIRouter()


@router.get("/welcome", response_class=HTMLResponse, include_in_schema=False)
async def welcome(request: Request, settings: SettingsDep) -> HTMLResponse:
    return render(request, "pages/welcome.html", shell_context(settings, None, "welcome"))


@router.post("/seed-demo", include_in_schema=False)
async def seed_demo(settings: SettingsDep) -> RedirectResponse:
    """Idempotently populate people/demo/db.sqlite with synthetic jobs."""
    from matchbox.web.demo import seed_demo_profile

    seed_demo_profile(settings)
    return RedirectResponse(url="/p/demo/inbox", status_code=303)
