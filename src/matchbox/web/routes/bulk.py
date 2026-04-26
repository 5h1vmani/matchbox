"""Bulk action endpoints — selection-bar operations on multiple jobs.

Selected job IDs are POSTed as repeated `id` form fields.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.schema import VALID_STATES
from matchbox.web.deps import ProfileDep
from matchbox.web.render import render
from matchbox.web.routes.jobs import build_inbox_context

router = APIRouter()


@router.post("/state", response_class=HTMLResponse)
async def bulk_state(
    request: Request,
    profile: ProfileDep,
    new_state: Annotated[str, Form()],
    id: Annotated[list[int] | None, Form()] = None,
) -> HTMLResponse:
    if new_state not in VALID_STATES:
        raise HTTPException(400, f"Invalid state '{new_state}'")
    ids = id or []
    for jid in ids:
        db.update_job_state(profile, jid, new_state)
    ctx = build_inbox_context(profile, request.query_params)
    ctx["active_profile"] = profile
    ctx["toast"] = f"{len(ids)} job(s) → {new_state}"
    return render(request, "components/_job_rows.html", ctx)


@router.post("/star", response_class=HTMLResponse)
async def bulk_star(
    request: Request,
    profile: ProfileDep,
    id: Annotated[list[int] | None, Form()] = None,
) -> HTMLResponse:
    ids = id or []
    for jid in ids:
        db.toggle_star(profile, jid)
    ctx = build_inbox_context(profile, request.query_params)
    ctx["active_profile"] = profile
    ctx["toast"] = f"{len(ids)} job(s) toggled"
    return render(request, "components/_job_rows.html", ctx)
