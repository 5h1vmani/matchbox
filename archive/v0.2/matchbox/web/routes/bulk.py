"""Bulk action endpoints — selection-bar operations on multiple jobs.

Selected job IDs are POSTed as repeated `id` form fields.

Bulk Tailor (item #1, M4 fix): runs in a FastAPI BackgroundTask so the
HTTP request returns immediately and the UI polls /bulk/tailor/{task_id}
for progress. Capped at MAX_BULK_TAILOR jobs so total cost is bounded.
For larger batches use the CLI:
    matchbox tailor <profile> <id> [<id> ...]
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.person import load_person
from matchbox.core.schema import VALID_STATES, Person
from matchbox.web import tasks
from matchbox.web.deps import ProfileDep, SettingsDep
from matchbox.web.render import render
from matchbox.web.routes.jobs import build_inbox_context
from matchbox.web.tailor_view import estimate, run

router = APIRouter()
log = logging.getLogger(__name__)

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
    starred_after = 0
    for jid in ids:
        if db.toggle_star(profile, jid):
            starred_after += 1
    ctx = build_inbox_context(profile, request.query_params)
    ctx["active_profile"] = profile
    if starred_after == len(ids):
        msg = f"{len(ids)} job(s) starred"
    elif starred_after == 0:
        msg = f"{len(ids)} job(s) unstarred"
    else:
        msg = f"{starred_after} starred · {len(ids) - starred_after} unstarred"
    return render(request, "components/_job_rows.html", ctx, toast=msg)


# ──────────────────────────────────────────────
# Bulk tailor (background task + polling)
# ──────────────────────────────────────────────


@router.post("/tailor/preview", response_class=HTMLResponse)
async def bulk_tailor_preview(
    request: Request,
    settings: SettingsDep,
    profile: ProfileDep,
    id: Annotated[list[int] | None, Form()] = None,
) -> HTMLResponse:
    """Cumulative cost preview before bulk tailor execution."""
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


def _run_bulk_tailor(profile: str, person: Person, task_id: str, ids: list[int]) -> None:
    """Background worker — runs in a thread via FastAPI BackgroundTasks."""
    tasks.set_status(task_id, "running")
    total_cost = 0.0
    failures = 0
    for idx, jid in enumerate(ids):
        tasks.update_item(task_id, idx, status="running")
        job = db.get_job(profile, jid)
        if job is None:
            tasks.update_item(task_id, idx, status="failed", detail="job not found")
            failures += 1
            continue
        try:
            outcome = run(job, person)
        except Exception as e:  # noqa: BLE001
            log.exception("bulk tailor failed for job_id=%s", jid)
            tasks.update_item(task_id, idx, status="failed", detail=str(e))
            failures += 1
            continue

        if outcome.error:
            tasks.update_item(task_id, idx, status="failed", detail=outcome.error)
            failures += 1
        elif outcome.application:
            cost = outcome.application.cost_usd
            total_cost += cost
            tasks.update_item(
                task_id,
                idx,
                status="ok",
                detail=f"{outcome.application.tier} · ${cost:.4f}"
                + (f" · {len(outcome.violations)} gate" if outcome.violations else ""),
                extra={
                    "tier": outcome.application.tier,
                    "cost": cost,
                    "violations": len(outcome.violations),
                },
            )
        else:
            tasks.update_item(task_id, idx, status="skipped", detail="skip tier")

    final: tasks.TaskStatus = "failed" if failures == len(ids) else "done"
    tasks.set_status(
        task_id,
        final,
        summary={"total_cost": total_cost, "failures": failures, "total": len(ids)},
    )


@router.post("/tailor", response_class=HTMLResponse)
async def bulk_tailor_execute(
    request: Request,
    settings: SettingsDep,
    profile: ProfileDep,
    background: BackgroundTasks,
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

    jobs = [j for j in (db.get_job(profile, jid) for jid in ids) if j is not None]
    high = sum(estimate(j).high_usd for j in jobs)
    if high >= settings.cost_confirm_threshold_usd and confirmed != "1":
        raise HTTPException(412, "Cost confirmation required for bulk tailor.")

    person = load_person(profile)
    items = [tasks.TaskItem(label=f"{j.company} — {j.role}") for j in jobs]
    task = tasks.create("bulk_tailor", items)
    background.add_task(_run_bulk_tailor, profile, person, task.id, [j.id or 0 for j in jobs])

    return render(
        request,
        "components/_bulk_tailor_progress.html",
        {"active_profile": profile, "task": task},
    )


@router.get("/tailor/{task_id}", response_class=HTMLResponse)
async def bulk_tailor_status(request: Request, profile: ProfileDep, task_id: str) -> HTMLResponse:
    """Polling endpoint — returns the same template; HTMX refreshes itself
    every 1.5s until the task is terminal."""
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(404, "Task not found (may have been cleaned up).")
    return render(
        request,
        "components/_bulk_tailor_progress.html",
        {"active_profile": profile, "task": task},
    )
