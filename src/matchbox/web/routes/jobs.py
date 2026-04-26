"""Per-job HTMX endpoints — partial swaps for table rows and the detail panel.

Routes (all under /p/{profile}/jobs):
    GET  /              -> rows partial (filtered table body)
    GET  /{id}/detail   -> slide-out detail panel
    POST /{id}/star     -> toggle star, return updated row
    POST /{id}/state    -> change state, return updated row + panel
    POST /{id}/response -> log response, return updated panel
    GET  /{id}/tailor/preview -> cost preview before tailor (phase 4)
    POST /{id}/tailor   -> run tailor, return updated panel + row (phase 4)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.core import db
from matchbox.core.schema import VALID_RESPONSE_TYPES, VALID_STATES, Job
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


def parse_filters(qs: Any) -> dict[str, Any]:
    """Parse query params into list_jobs kwargs. Tolerant of missing/empty."""
    states = [s for s in _qs_get_list(qs, "state") if s in VALID_STATES] or None
    tiers = [t for t in _qs_get_list(qs, "tier") if t] or None
    countries = [c for c in _qs_get_list(qs, "country") if c] or None
    min_score = _qs_get_one(qs, "min_score") or None
    role_search = _qs_get_one(qs, "q") or None
    starred = True if _qs_get_one(qs, "starred") == "1" else None
    order_key = _qs_get_one(qs, "order") or "score"
    order_by = _VALID_ORDERS.get(order_key, _VALID_ORDERS["score"])

    return {
        "_states": states,
        "_tiers": tiers,
        "_countries": countries,
        "_min_score": float(min_score) if min_score else None,
        "_role_search": role_search,
        "_starred": starred,
        "_order_by": order_by,
        "_order_key": order_key,
    }


def _query_jobs(profile: str, f: dict[str, Any]) -> list[Job]:
    jobs = db.list_jobs(
        profile,
        state=f["_states"],
        country=f["_countries"],
        min_score=f["_min_score"],
        is_starred=f["_starred"],
        role_search=f["_role_search"],
        limit=500,
        order_by=f["_order_by"],
    )
    if f["_tiers"]:
        jobs = [j for j in jobs if j.tier in f["_tiers"]]
    return jobs


def build_inbox_context(profile: str, qs: Any) -> dict[str, Any]:
    """Shared by full-page + rows partial — guarantees identical state."""
    f = parse_filters(qs)
    jobs = _query_jobs(profile, f)
    stats = db.get_stats(profile)
    return {
        "jobs": jobs,
        "stats": stats,
        "filter_states": f["_states"] or [],
        "filter_tiers": f["_tiers"] or [],
        "filter_min_score": f["_min_score"] or 0.0,
        "filter_q": f["_role_search"] or "",
        "filter_starred": bool(f["_starred"]),
        "order_key": f["_order_key"],
        "valid_states": sorted(VALID_STATES),
        "valid_tiers": ["bespoke", "template", "canonical", "skip"],
        "valid_response_types": sorted(VALID_RESPONSE_TYPES),
    }


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def rows_partial(request: Request, profile: ProfileDep) -> HTMLResponse:
    ctx = build_inbox_context(profile, request.query_params)
    ctx["active_profile"] = profile
    return render(request, "components/_job_rows.html", ctx)


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
) -> HTMLResponse:
    if new_state not in VALID_STATES:
        raise HTTPException(400, f"Invalid state '{new_state}'")
    db.update_job_state(profile, job_id, new_state, note=note)
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
            "toast": f"Marked {new_state}",
        },
    )


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
    from matchbox.outcome.response import log_response as _log

    _log(profile, job_id, response_type=response_type, response_date=response_date, note=note)
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
            "toast": f"Logged {response_type}",
        },
    )


# Tailor endpoints intentionally deferred to phase 4.
