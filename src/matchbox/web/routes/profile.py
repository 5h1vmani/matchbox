"""Profile editor endpoints — live-tunable scoring weights.

Phase 6 fills out preview + save flow. Stub now so the page renders.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from matchbox.web.deps import ProfileDep

router = APIRouter()


@router.get("/preview", response_class=HTMLResponse)
async def preview(request: Request, profile: ProfileDep) -> HTMLResponse:
    return HTMLResponse("<div class='text-slate-500'>Preview coming in phase 6.</div>")
