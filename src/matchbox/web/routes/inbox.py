"""Inbox / triage UI.

Lists scored jobs, lets the user pick which to tailor, then writes a
work-queue.json the brain will pick up.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from matchbox.scoring.rubric import score_all_new
from matchbox.scoring.runs import JobSelection, create_run
from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()

PALETTES = ["slate", "ink", "forest", "claret", "bronze"]
FONTS = ["source-serif", "source-sans", "inter", "atkinson-hyperlegible"]

# Statuses the triage screen surfaces. Tailored / applied jobs live in
# the review-run screen (M6).
TRIAGE_STATUSES = ("new", "scored", "selected", "skipped", "rejected")


def _list_jobs(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    min_score: float | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    where = ["status IN ('new', 'scored', 'selected', 'skipped', 'rejected')"]
    params: list[object] = []
    if status and status in TRIAGE_STATUSES:
        where = [f"status = '{status}'"]
    if min_score is not None:
        where.append("score >= ?")
        params.append(min_score)
    if q:
        where.append("(company LIKE ? OR title LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    sql = f"""
        SELECT id, company, title, location, url, apply_url, jd_text,
               status, score, score_breakdown_json
          FROM job
         WHERE {' AND '.join(where)}
         ORDER BY COALESCE(score, 0) DESC, id DESC
    """
    rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["breakdown"] = (
            json.loads(d["score_breakdown_json"]) if d["score_breakdown_json"] else None
        )
        out.append(d)
    return out


@router.get("/inbox", response_class=HTMLResponse)
def inbox_index(
    request: Request,
    conn: ConnDep,
    status: str | None = None,
    min_score: float | None = None,
    q: str | None = None,
) -> HTMLResponse:
    jobs = _list_jobs(conn, status=status, min_score=min_score, q=q)
    counts = {
        s: conn.execute("SELECT COUNT(*) FROM job WHERE status = ?", (s,)).fetchone()[0]
        for s in TRIAGE_STATUSES + ("tailored", "applied")
    }
    return templates.TemplateResponse(
        request,
        "inbox/index.html.j2",
        {
            "jobs": jobs,
            "counts": counts,
            "palettes": PALETTES,
            "fonts": FONTS,
            "filter_status": status,
            "filter_min_score": min_score,
            "filter_q": q,
        },
    )


@router.post("/inbox/score-all", response_class=HTMLResponse)
def score_all(request: Request, conn: ConnDep) -> HTMLResponse:
    n = score_all_new(conn)
    return HTMLResponse(
        f"""<span id="score-status" class="text-xs text-success">scored {n} new job{'' if n == 1 else 's'}</span>"""
    )


@router.post("/inbox/jobs", response_class=HTMLResponse)
def add_job_manually(
    request: Request,
    conn: ConnDep,
    company: Annotated[str, Form()],
    title: Annotated[str, Form()],
    url: Annotated[str, Form()],
    jd_text: Annotated[str, Form()],
    apply_url: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Add a job by hand from a URL + pasted JD text.

    For LinkedIn, company careers pages, friend referrals, and anything
    not covered by a polled ATS source. The row lands with
    `source = NULL` and `status = 'new'` so the existing score / triage
    / run flow picks it up like any other job.
    """
    company_s = company.strip()
    title_s = title.strip()
    url_s = url.strip()
    jd_text_s = jd_text.strip()
    if not (company_s and title_s and url_s and jd_text_s):
        raise HTTPException(
            status_code=400,
            detail="company, title, url, and jd_text are all required",
        )
    try:
        cur = conn.execute(
            """
            INSERT INTO job
                (source, company, title, location, url, apply_url, jd_text, status)
            VALUES (NULL, ?, ?, ?, ?, ?, ?, 'new')
            """,
            (
                company_s,
                title_s,
                (location.strip() or None),
                url_s,
                (apply_url.strip() or None),
                jd_text_s,
            ),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail=f"a job with url {url_s!r} already exists in the inbox",
        ) from e
    job_id = cur.lastrowid
    return HTMLResponse(
        f'<span id="add-job-status" class="text-xs text-success">'
        f'job #{job_id} added. Click "Score new jobs" to score it.</span>'
    )


VALID_TRANSITIONS: set[str] = {"skipped", "rejected", "scored"}


@router.post("/inbox/jobs/{job_id}/status", response_class=HTMLResponse)
def set_job_status(
    request: Request,
    job_id: int,
    conn: ConnDep,
    to: Annotated[str, Form()],
) -> HTMLResponse:
    """Move a job between triage statuses.

    Allowed targets: skipped (I do not want to apply now), rejected (no),
    scored (re-open something I previously skipped or rejected). Selected
    / tailored / applied happen elsewhere in the flow and are not user-
    settable from here.
    """
    if to not in VALID_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"cannot transition to {to!r}")
    row = conn.execute("SELECT status FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    if row["status"] in ("tailored", "applied"):
        raise HTTPException(
            status_code=409,
            detail=f"job {job_id} is already {row['status']}; reset from /runs",
        )
    conn.execute("UPDATE job SET status = ? WHERE id = ?", (to, job_id))
    # Return just the updated row fragment so HTMX can swap one row.
    jobs = _list_jobs(conn)
    updated = next((j for j in jobs if j["id"] == job_id), None)
    if updated is None:
        # The row may have left the triage filter (e.g. moved to 'tailored').
        return HTMLResponse(status_code=200, content="")
    return templates.TemplateResponse(request, "inbox/_job_row.html.j2", {"job": updated})


@router.post("/runs", response_class=HTMLResponse)
def start_run(
    request: Request,
    conn: ConnDep,
    job_ids: Annotated[list[int], Form()],
    want_cv: Annotated[list[int] | None, Form()] = None,
    want_cover: Annotated[list[int] | None, Form()] = None,
    palette: Annotated[str, Form()] = "slate",
    font: Annotated[str, Form()] = "source-serif",
) -> HTMLResponse:
    want_cv_list = want_cv or []
    want_cover_list = want_cover or []
    if palette not in PALETTES:
        raise HTTPException(status_code=400, detail=f"unknown palette: {palette}")
    if font not in FONTS:
        raise HTTPException(status_code=400, detail=f"unknown font: {font}")
    want_cv_set = set(want_cv_list)
    want_cover_set = set(want_cover_list)
    selections: list[JobSelection] = []
    for jid in job_ids:
        cv = jid in want_cv_set
        cover = jid in want_cover_set
        if cv or cover:
            selections.append(JobSelection(job_id=jid, want_cv=cv, want_cover=cover))
    if not selections:
        raise HTTPException(
            status_code=400,
            detail="select at least one job — toggle CV or cover for it",
        )

    run_id, path = create_run(conn, selections=selections, palette=palette, font=font)
    return templates.TemplateResponse(
        request,
        "inbox/_run_started.html.j2",
        {
            "run_id": run_id,
            "work_queue_path": str(path),
            "job_count": len(selections),
        },
    )
