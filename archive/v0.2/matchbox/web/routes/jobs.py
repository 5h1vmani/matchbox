"""Per-job HTMX endpoints — partial swaps for table rows and the detail panel.

Routes (all under /p/{profile}/jobs):
    GET  /                    -> rows partial (filtered table body)
    GET  /{id}/detail         -> slide-out detail panel
    POST /{id}/star           -> toggle star, return updated row
    POST /{id}/state          -> change state, return updated row + panel
    POST /{id}/response       -> log response, return updated panel
    GET  /{id}/jd             -> full JD text partial (lazy load)
    GET  /{id}/responses      -> response history partial (lazy load)
    GET  /{id}/tailor/preview -> cost preview before tailor
    POST /{id}/tailor         -> run tailor, return updated panel + row
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, TypedDict
from urllib.parse import parse_qs

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.schema import VALID_RESPONSE_TYPES, VALID_STATES, Job
from matchbox.outcome.response import log_response as _log_response
from matchbox.web.deps import ProfileDep
from matchbox.web.render import render

router = APIRouter()


# ──────────────────────────────────────────────
# Filter parsing — single source of truth so inbox + rows endpoint agree
# ──────────────────────────────────────────────

_VALID_ORDERS: dict[str, str] = {
    "score": "total_score DESC",
    "score_asc": "total_score ASC",
    "newest": "discovered_date DESC",
    "company": "company ASC",
    "state": "state ASC",
    "starred": "starred_first",
}

ROW_LIMIT = 500


class ParsedFilters(TypedDict):
    """Typed payload from `parse_filters` — used by both inbox and rows endpoints.

    Keys are SQL-shaped (states, country, etc.) so they pass straight to
    db.list_jobs(**); the `_order_key` and `_role_search` mirror UI state.
    """

    states: list[str] | None
    tiers: list[str] | None
    countries: list[str] | None
    min_score: float | None
    role_search: str | None
    starred: bool | None
    order_by: str
    order_key: str


def _qs_get_list(qs: Any, key: str) -> Sequence[str]:
    """Return all values for `key` (Starlette QueryParams or dict-of-lists)."""
    if hasattr(qs, "getlist"):
        return list(qs.getlist(key))
    parsed = parse_qs(str(qs))
    return parsed.get(key, [])


def _qs_get_one(qs: Any, key: str) -> str | None:
    if hasattr(qs, "get"):
        val = qs.get(key)
        return val if isinstance(val, str) else None
    parsed = parse_qs(str(qs))
    values = parsed.get(key) or []
    return values[0] if values else None


def parse_filters(qs: Any) -> ParsedFilters:
    """Parse query params into list_jobs kwargs. Tolerant of missing/empty."""
    states = [s for s in _qs_get_list(qs, "state") if s in VALID_STATES] or None
    tiers = [t for t in _qs_get_list(qs, "tier") if t] or None
    countries = [c for c in _qs_get_list(qs, "country") if c] or None
    min_score_raw = _qs_get_one(qs, "min_score")
    role_search = _qs_get_one(qs, "q") or None
    starred = True if _qs_get_one(qs, "starred") == "1" else None
    order_key = _qs_get_one(qs, "order") or "score"
    order_by = _VALID_ORDERS.get(order_key, _VALID_ORDERS["score"])

    return ParsedFilters(
        states=states,
        tiers=tiers,
        countries=countries,
        min_score=float(min_score_raw) if min_score_raw else None,
        role_search=role_search,
        starred=starred,
        order_by=order_by,
        order_key=order_key,
    )


def _query_jobs(profile: str, f: ParsedFilters) -> list[Job]:
    jobs = db.list_jobs(
        profile,
        state=f["states"],
        country=f["countries"],
        min_score=f["min_score"],
        is_starred=f["starred"],
        role_search=f["role_search"],
        limit=ROW_LIMIT,
        order_by=f["order_by"],
    )
    if f["tiers"]:
        jobs = [j for j in jobs if j.tier in f["tiers"]]
    return jobs


def build_inbox_context(profile: str, qs: Any) -> dict[str, Any]:
    """Shared by full-page + rows partial — guarantees identical state."""
    f = parse_filters(qs)
    jobs = _query_jobs(profile, f)
    stats = db.get_stats(profile)
    # Surface "showing X of Y" when the limit truncates results, so the
    # operator never silently misses jobs (item #13 from the audit).
    truncated = len(jobs) >= ROW_LIMIT
    return {
        "jobs": jobs,
        "stats": stats,
        "filter_states": f["states"] or [],
        "filter_tiers": f["tiers"] or [],
        "filter_min_score": f["min_score"] or 0.0,
        "filter_q": f["role_search"] or "",
        "filter_starred": bool(f["starred"]),
        "order_key": f["order_key"],
        "valid_states": sorted(VALID_STATES),
        "valid_tiers": ["bespoke", "template", "canonical", "skip"],
        "valid_response_types": sorted(VALID_RESPONSE_TYPES),
        "row_limit": ROW_LIMIT,
        "truncated": truncated,
        "active_filters": _active_filter_chips(f),
    }


def _active_filter_chips(f: ParsedFilters) -> list[dict[str, str]]:
    """List of {label, param, value} for visible filter chips.

    The template builds a remove URL by stripping (param, value) from the
    current query string. If `value` is empty the whole param is removed.
    """
    chips: list[dict[str, str]] = []
    for s in f["states"] or []:
        chips.append({"label": f"state: {s.replace('_', ' ')}", "param": "state", "value": s})
    for t in f["tiers"] or []:
        chips.append({"label": f"tier: {t}", "param": "tier", "value": t})
    if f["min_score"]:
        chips.append({"label": f"score ≥ {f['min_score']}", "param": "min_score", "value": ""})
    if f["role_search"]:
        chips.append({"label": f"“{f['role_search']}”", "param": "q", "value": ""})
    if f["starred"]:
        chips.append({"label": "starred", "param": "starred", "value": ""})
    return chips


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def rows_partial(request: Request, profile: ProfileDep) -> HTMLResponse:
    """Filtered table rows. Sends `HX-Push-Url` so the browser address bar
    reflects the canonical inbox URL with current filters (bookmarkable),
    even though the response itself is just the rows partial."""
    ctx = build_inbox_context(profile, request.query_params)
    ctx["active_profile"] = profile
    response = render(request, "components/_job_rows.html", ctx)
    qs = str(request.query_params)
    inbox_url = f"/p/{profile}/inbox" + (f"?{qs}" if qs else "")
    response.headers["HX-Push-Url"] = inbox_url
    return response


@router.get("/{job_id}/detail", response_class=HTMLResponse)
async def detail(request: Request, profile: ProfileDep, job_id: int) -> HTMLResponse:
    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return render(
        request,
        "components/job_detail.html",
        {
            "job": job,
            "active_profile": profile,
            "valid_response_types": sorted(VALID_RESPONSE_TYPES),
        },
    )


@router.post("/{job_id}/star", response_class=HTMLResponse)
async def star(request: Request, profile: ProfileDep, job_id: int) -> HTMLResponse:
    db.toggle_star(profile, job_id)
    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return render(
        request,
        "components/job_row.html",
        {"job": job, "active_profile": profile},
    )


@router.post("/{job_id}/state", response_class=HTMLResponse)
async def change_state(
    request: Request,
    profile: ProfileDep,
    job_id: int,
    new_state: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
    prev_state: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    if new_state not in VALID_STATES:
        raise HTTPException(400, f"Invalid state '{new_state}'")
    job_before = db.get_job(profile, job_id)
    if job_before is None:
        raise HTTPException(404, "Job not found")
    actual_prev = prev_state or job_before.state

    db.update_job_state(profile, job_id, new_state, note=note)
    job_after = db.get_job(profile, job_id)
    assert job_after is not None  # we just verified it exists

    # Item #15: undo for destructive state changes (anything that hides
    # or rejects the job). The toast offers a one-click revert.
    destructive = new_state in {"discarded", "rejected", "skip"}
    return render(
        request,
        "components/job_detail.html",
        {
            "job": job_after,
            "active_profile": profile,
            "valid_response_types": sorted(VALID_RESPONSE_TYPES),
        },
        toast=_state_toast(new_state),
        toast_level="info",
        undo_url=(f"/p/{profile}/jobs/{job_id}/state" if destructive and actual_prev else None),
        undo_payload=({"new_state": actual_prev} if destructive and actual_prev else None),
    )


def _state_toast(new_state: str) -> str:
    nice = new_state.replace("_", " ")
    next_hints = {
        "applied": "Applied — log when you hear back.",
        "queued_for_tailor": "Queued for tailor.",
        "discarded": "Discarded.",
        "tailored": "Tailored — review the PDF, then mark applied.",
    }
    return next_hints.get(new_state, f"Marked {nice}.")


@router.post("/{job_id}/response", response_class=HTMLResponse)
async def log_response(
    request: Request,
    profile: ProfileDep,
    job_id: int,
    response_type: Annotated[str, Form()],
    response_date: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    if response_type not in VALID_RESPONSE_TYPES:
        raise HTTPException(400, f"Invalid response_type '{response_type}'")
    _log_response(
        profile, job_id, response_type=response_type, response_date=response_date, note=note
    )
    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    next_hint = {
        "interview": "Logged — log offer or rejection when you hear back.",
        "offer": "Offer logged. Congrats.",
        "rejection": "Rejection logged.",
        "ghosted": "Ghosted logged.",
    }.get(response_type, f"Logged {response_type}.")
    return render(
        request,
        "components/job_detail.html",
        {
            "job": job,
            "active_profile": profile,
            "valid_response_types": sorted(VALID_RESPONSE_TYPES),
        },
        toast=next_hint,
        toast_level="success" if response_type in ("interview", "offer") else "info",
    )


@router.get("/{job_id}/jd", response_class=HTMLResponse)
async def jd_full(request: Request, profile: ProfileDep, job_id: int) -> HTMLResponse:
    """Full JD text partial — lazy-loaded so the detail panel stays fast."""
    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    body = (job.jd_text or job.jd_summary or "").strip()
    if not body:
        return HTMLResponse('<div class="text-xs text-slate-400">No JD text on file.</div>')
    return render(request, "components/_jd_full.html", {"job": job, "body": body})


@router.get("/{job_id}/responses", response_class=HTMLResponse)
async def responses_history(request: Request, profile: ProfileDep, job_id: int) -> HTMLResponse:
    """Response history (item #20) — lazy-loaded under the panel."""
    rows = db.get_responses(profile, job_id=job_id)
    return render(request, "components/_responses.html", {"responses": rows})


# ──────────────────────────────────────────────
# Tailor flow — preview → confirm → execute
# ──────────────────────────────────────────────


@router.get("/{job_id}/tailor/preview", response_class=HTMLResponse)
async def tailor_preview(request: Request, profile: ProfileDep, job_id: int) -> HTMLResponse:
    from matchbox.web.deps import get_settings
    from matchbox.web.tailor_view import alternative_tier, estimate

    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    est = estimate(job)
    settings = get_settings()
    return render(
        request,
        "components/_tailor_preview.html",
        {
            "job": job,
            "active_profile": profile,
            "estimate": est,
            "alt_tier": alternative_tier(est.tier),
            "needs_confirm": est.needs_confirmation(settings.cost_confirm_threshold_usd),
            "threshold": settings.cost_confirm_threshold_usd,
        },
    )


@router.post("/{job_id}/tailor", response_class=HTMLResponse)
async def tailor_execute(
    request: Request,
    profile: ProfileDep,
    job_id: int,
    tier_override: Annotated[str | None, Form()] = None,
    confirmed: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    from matchbox.core.person import load_person
    from matchbox.web.deps import get_settings
    from matchbox.web.tailor_view import estimate, run

    job = db.get_job(profile, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    settings = get_settings()
    est = estimate(job.model_copy(update={"tier": tier_override}) if tier_override else job)
    if est.needs_confirmation(settings.cost_confirm_threshold_usd) and confirmed != "1":
        raise HTTPException(412, "Cost confirmation required")

    person = load_person(profile)
    outcome = run(job, person, tier_override=tier_override)

    job_after = db.get_job(profile, job_id)
    from matchbox.web.render import ToastLevel

    level: ToastLevel
    if outcome.error:
        toast_msg = f"Tailor failed: {outcome.error}"
        level = "error"
    elif outcome.application:
        toast_msg = f"Tailored as {outcome.application.tier}. Review the PDF, then mark applied."
        level = "success"
    else:
        toast_msg = "Skipped (skip tier)."
        level = "info"

    return render(
        request,
        "components/job_detail.html",
        {
            "job": job_after,
            "active_profile": profile,
            "valid_response_types": sorted(VALID_RESPONSE_TYPES),
            "tailor_outcome": outcome,
        },
        toast=toast_msg,
        toast_level=level,
    )
