"""Bulk action endpoints — selection-bar operations on multiple jobs.

Selected job IDs are POSTed as repeated `id` form fields.

Bulk Tailor (item #1): synchronous execution capped at MAX_BULK_TAILOR jobs
to bound cost and request time. For larger batches use the CLI:
    matchbox tailor <profile> <id> [<id> ...]
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.person import load_person
from matchbox.core.schema import VALID_STATES
from matchbox.web.deps import ProfileDep, SettingsDep
from matchbox.web.render import render
from matchbox.web.routes.jobs import build_inbox_context
from matchbox.web.tailor_view import estimate, run

router = APIRouter()

MAX_BULK_TAILOR = 5


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
    return render(
        request,
        "components/_job_rows.html",
        ctx,
        toast=f"{len(ids)} job(s) → {new_state.replace('_', ' ')}",
    )


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
    return render(
        request,
        "components/_job_rows.html",
        ctx,
        toast=f"{len(ids)} job(s) toggled",
    )


# ──────────────────────────────────────────────
# Bulk tailor (item #1)
# ──────────────────────────────────────────────


@router.post("/tailor/preview", response_class=HTMLResponse)
async def bulk_tailor_preview(
    request: Request,
    settings: SettingsDep,
    profile: ProfileDep,
    id: Annotated[list[int] | None, Form()] = None,
) -> HTMLResponse:
    """Cumulative cost preview before bulk tailor execution. Returns a
    confirmation modal partial that the operator must POST to /tailor."""
    ids = id or []
    if not ids:
        raise HTTPException(400, "Select at least one job to tailor.")

    jobs = [j for j in (db.get_job(profile, jid) for jid in ids) if j is not None]
    estimates = [(j, estimate(j)) for j in jobs]

    low = sum(e.low_usd for _, e in estimates)
    high = sum(e.high_usd for _, e in estimates)
    over_cap = len(ids) > MAX_BULK_TAILOR
    needs_confirm = high >= settings.cost_confirm_threshold_usd

    return render(
        request,
        "components/_bulk_tailor_preview.html",
        {
            "active_profile": profile,
            "estimates": estimates,
            "ids": ids,
            "low": low,
            "high": high,
            "over_cap": over_cap,
            "max_cap": MAX_BULK_TAILOR,
            "needs_confirm": needs_confirm,
            "threshold": settings.cost_confirm_threshold_usd,
        },
    )


@router.post("/tailor", response_class=HTMLResponse)
async def bulk_tailor_execute(
    request: Request,
    settings: SettingsDep,
    profile: ProfileDep,
    id: Annotated[list[int] | None, Form()] = None,
    confirmed: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    ids = id or []
    if not ids:
        raise HTTPException(400, "No jobs selected.")
    if len(ids) > MAX_BULK_TAILOR:
        raise HTTPException(
            400,
            f"Bulk tailor capped at {MAX_BULK_TAILOR}. Use the CLI for larger batches.",
        )

    # Cumulative cost confirmation.
    jobs = [j for j in (db.get_job(profile, jid) for jid in ids) if j is not None]
    high = sum(estimate(j).high_usd for j in jobs)
    if high >= settings.cost_confirm_threshold_usd and confirmed != "1":
        raise HTTPException(412, "Cost confirmation required for bulk tailor.")

    person = load_person(profile)
    results: list[dict[str, object]] = []
    total_cost = 0.0
    failures = 0
    for j in jobs:
        outcome = run(j, person)
        if outcome.error:
            failures += 1
            results.append({"job": j, "status": "failed", "detail": outcome.error})
        elif outcome.application:
            total_cost += outcome.application.cost_usd
            results.append(
                {
                    "job": j,
                    "status": "ok",
                    "tier": outcome.application.tier,
                    "cost": outcome.application.cost_usd,
                    "violations": len(outcome.violations),
                }
            )
        else:
            results.append({"job": j, "status": "skipped"})

    toast = f"Tailored {len(jobs) - failures}/{len(jobs)} · spent ${total_cost:.2f}"
    return render(
        request,
        "components/_bulk_tailor_result.html",
        {"active_profile": profile, "results": results, "total_cost": total_cost},
        toast=toast,
        toast_level="error" if failures else "success",
    )
