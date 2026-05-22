"""Review-run screen — live status, PDF preview, apply link.

After the user clicks "Start tailoring" in /inbox, the app writes
work-queue.json into runs/<id>/. The brain processes the queue and
writes status.json. This screen polls status.json (HTMX) and renders
per-job cards as the brain progresses.

PDF serving is sandboxed: a route bound to runs/<run-id>/output/
that resolves paths and refuses anything that escapes that directory.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from jsonschema import Draft202012Validator

from matchbox.assemble import drift_check, re_render_cv
from matchbox.core.db import PROJECT_ROOT
from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

PALETTES = ["slate", "ink", "forest", "claret", "bronze"]
FONTS = ["source-serif", "source-sans", "inter", "atkinson-hyperlegible"]

router = APIRouter()

RUNS_DIR = PROJECT_ROOT / "runs"
STATUS_SCHEMA = json.loads(
    (PROJECT_ROOT / "schemas" / "status.v1.json").read_text(encoding="utf-8")
)
_STATUS_VALIDATOR = Draft202012Validator(STATUS_SCHEMA)


def _load_status(run_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (payload | None, validation_errors).

    A mid-write JSONDecodeError yields a synthetic error placeholder so
    the next poll catches the finished file. A schema_version mismatch
    yields a single error and a None payload (no point parsing further).
    Other schema violations are surfaced as a banner — we still render
    the page so the user can see partial progress.
    """
    path = RUNS_DIR / run_id / "status.json"
    if not path.exists():
        return None, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        placeholder = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "error",
            "error": f"status.json is mid-write or malformed: {e}",
            "jobs": [],
        }
        return placeholder, []
    if payload.get("schema_version") != 1:
        return None, [
            f"status.json schema_version mismatch: got "
            f"{payload.get('schema_version')!r}, expected 1"
        ]
    errors = sorted(_STATUS_VALIDATOR.iter_errors(payload), key=lambda e: list(e.absolute_path))
    error_messages = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    ]
    result: dict[str, Any] = payload
    return result, error_messages


def _list_run_jobs(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT rj.job_id, rj.want_cv, rj.want_cover, rj.palette, rj.font,
               j.company, j.title, j.apply_url, j.url
          FROM run_job rj
          JOIN job j ON j.id = rj.job_id
         WHERE rj.run_id = ?
         ORDER BY rj.job_id
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _merge_job_state(
    queued_job: dict[str, Any], status_job: dict[str, Any] | None
) -> dict[str, Any]:
    """Combine the queue row with any brain status — status fields win."""
    merged: dict[str, Any] = {
        **queued_job,
        "cv_status": "pending",
        "cover_status": "pending",
        "cv_path": None,
        "cover_path": None,
        "gaps": [],
        "notes": None,
        "error": None,
    }
    if status_job is not None:
        merged.update(status_job)
    return merged


def _applied_state(conn: sqlite3.Connection, run_id: str, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT applied_at, status, response_type FROM application WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchone()
    return dict(row) if row else None


# ─── routes ────────────────────────────────────────────────────────────


@router.get("/review-run/{run_id}", response_class=HTMLResponse)
def review_run_index(request: Request, run_id: str, conn: ConnDep) -> HTMLResponse:
    run = conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id}")
    queued = _list_run_jobs(conn, run_id)
    status, status_errors = _load_status(run_id)
    status_jobs = {j["job_id"]: j for j in (status or {}).get("jobs", [])}
    jobs = [
        {
            **_merge_job_state(q, status_jobs.get(q["job_id"])),
            "applied": _applied_state(conn, run_id, q["job_id"]),
        }
        for q in queued
    ]
    return templates.TemplateResponse(
        request,
        "review_run/index.html.j2",
        {
            "run": dict(run),
            "status": status,
            "status_errors": status_errors,
            "jobs": jobs,
        },
    )


def _drift_for_job(conn: sqlite3.Connection, run_id: str, job_id: int) -> list[dict[str, Any]]:
    cv_json_path = RUNS_DIR / run_id / "output" / str(job_id) / "cv.json"
    if not cv_json_path.exists():
        return []
    try:
        cv_json = json.loads(cv_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return drift_check(conn=conn, cv_json=cv_json)


@router.get("/review-run/{run_id}/jobs/{job_id}/card", response_class=HTMLResponse)
def job_card(
    request: Request,
    run_id: str,
    job_id: int,
    conn: ConnDep,
    drift: list[dict[str, Any]] | None = None,
) -> HTMLResponse:
    """Returns one job card. HTMX polls this every few seconds while
    the brain works."""
    queued = _list_run_jobs(conn, run_id)
    queued_one = next((q for q in queued if q["job_id"] == job_id), None)
    if queued_one is None:
        raise HTTPException(status_code=404, detail=f"no such (run, job): ({run_id}, {job_id})")
    status, _ = _load_status(run_id)
    status_job = next((j for j in (status or {}).get("jobs", []) if j["job_id"] == job_id), None)
    job = {
        **_merge_job_state(queued_one, status_job),
        "applied": _applied_state(conn, run_id, job_id),
    }
    if drift is None:
        drift = _drift_for_job(conn, run_id, job_id)
    return templates.TemplateResponse(
        request,
        "review_run/_job_card.html.j2",
        {"run_id": run_id, "job": job, "drift": drift},
    )


@router.post("/review-run/{run_id}/jobs/{job_id}/restyle", response_class=HTMLResponse)
def restyle_cv(
    request: Request,
    run_id: str,
    job_id: int,
    conn: ConnDep,
    palette: Annotated[str, Form()],
    font: Annotated[str, Form()],
) -> HTMLResponse:
    """Re-render the CV PDF with a new palette/font. No brain involved —
    cv.json is already on disk."""
    if palette not in PALETTES:
        raise HTTPException(status_code=400, detail=f"unknown palette: {palette}")
    if font not in FONTS:
        raise HTTPException(status_code=400, detail=f"unknown font: {font}")
    try:
        _, drift = re_render_cv(run_id=run_id, job_id=job_id, palette=palette, font=font, conn=conn)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    # Persist the new choice on the run_job row so the next render uses it.
    conn.execute(
        "UPDATE run_job SET palette = ?, font = ? WHERE run_id = ? AND job_id = ?",
        (palette, font, run_id, job_id),
    )
    if drift:
        # Stamp the run row so the card can surface a warning. Cheap and
        # visible — beats silently letting a stale CV ride.
        conn.execute(
            "UPDATE run SET status = CASE WHEN status = 'done' THEN 'done' ELSE status END "
            "WHERE id = ?",
            (run_id,),
        )
    return job_card(request=request, run_id=run_id, job_id=job_id, conn=conn, drift=drift)


@router.post("/review-run/{run_id}/jobs/{job_id}/applied", response_class=HTMLResponse)
def mark_applied(
    request: Request,
    run_id: str,
    job_id: int,
    conn: ConnDep,
    cv_path: Annotated[str, Form()] = "",
    cover_path: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Record that the user clicked Apply and submitted (manually)."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = conn.execute(
        "SELECT id FROM application WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE application SET status = 'applied', applied_at = ? WHERE id = ?",
            (now, existing[0]),
        )
    else:
        conn.execute(
            """
            INSERT INTO application (job_id, run_id, cv_path, cover_path, status, applied_at)
            VALUES (?, ?, ?, ?, 'applied', ?)
            """,
            (job_id, run_id, cv_path or None, cover_path or None, now),
        )
    conn.execute("UPDATE job SET status = 'applied' WHERE id = ?", (job_id,))
    # Re-render the card with applied state.
    return job_card(request=request, run_id=run_id, job_id=job_id, conn=conn)


# ─── abandon / delete run ─────────────────────────────────────────────


@router.post("/runs/{run_id}/abandon", response_class=HTMLResponse)
def abandon_run(request: Request, run_id: str, conn: ConnDep) -> HTMLResponse:
    """Mark a run dead so the user can move on.

    Sets run.status = 'error' (terminal — the index will stop polling
    pending cards). Any jobs that were 'selected' but never reached
    'tailored' or 'applied' fall back to 'scored' so they reappear in
    /inbox. Tailored / applied jobs are intentionally left in place —
    their artifacts still exist and the apply records still matter.
    """
    row = conn.execute("SELECT status FROM run WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id}")
    if row["status"] in ("done", "error"):
        # Already terminal; harmless no-op.
        return runs_index(request=request, conn=conn)
    conn.execute("UPDATE run SET status = 'error' WHERE id = ?", (run_id,))
    conn.execute(
        """
        UPDATE job
           SET status = 'scored'
         WHERE id IN (SELECT job_id FROM run_job WHERE run_id = ?)
           AND status = 'selected'
        """,
        (run_id,),
    )
    return runs_index(request=request, conn=conn)


@router.delete("/runs/{run_id}", response_class=Response)
def delete_run(run_id: str, conn: ConnDep) -> Response:
    """Delete a run row, its run_job links, its application rows, and
    its runs/<id>/ directory on disk.

    The job rows themselves stay — those came from ATS scans and belong
    to the inbox. Their .status field is reset to 'scored' so the user
    can re-queue them. cv.pdf / cover.pdf for an already-applied job
    are gone after this; the user is told so by the confirm dialog.
    """
    row = conn.execute("SELECT 1 FROM run WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id}")
    # Reset the jobs that were touched by this run.
    conn.execute(
        """
        UPDATE job
           SET status = CASE WHEN status IN ('selected', 'tailored') THEN 'scored' ELSE status END
         WHERE id IN (SELECT job_id FROM run_job WHERE run_id = ?)
        """,
        (run_id,),
    )
    conn.execute("DELETE FROM application WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM run_job WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM run WHERE id = ?", (run_id,))

    # Tear down the on-disk artifacts. Refuse to follow a symlink as the
    # run directory.
    run_dir = (RUNS_DIR / run_id).resolve()
    try:
        run_dir.relative_to(RUNS_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="run id escapes runs/") from e
    if run_dir.exists() and run_dir.is_dir():
        shutil.rmtree(run_dir)
    return Response(status_code=200)


# ─── sandboxed PDF serving ─────────────────────────────────────────────


@router.get("/runs/{run_id}/output/{job_id}/{filename}", include_in_schema=False)
def serve_run_file(run_id: str, job_id: int, filename: str) -> FileResponse:
    """Serve a file from runs/<run_id>/output/<job_id>/ only. Path-
    traversal is rejected by .resolve() + .relative_to() check."""
    if not filename or "/" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="bad filename")
    base = (RUNS_DIR / run_id / "output" / str(job_id)).resolve()
    if not base.exists():
        raise HTTPException(status_code=404, detail="run output not found")
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes run dir") from e
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"no such file: {filename}")
    if target.suffix.lower() not in {".pdf", ".json", ".md", ".txt"}:
        raise HTTPException(status_code=415, detail=f"refused type: {target.suffix}")
    media_type = "application/pdf" if target.suffix.lower() == ".pdf" else None
    return FileResponse(str(target), media_type=media_type)


@router.get("/runs", response_class=HTMLResponse)
def runs_index(request: Request, conn: ConnDep) -> HTMLResponse:
    rows = conn.execute(
        """
        SELECT r.id, r.created_at, r.status,
               (SELECT COUNT(*) FROM run_job WHERE run_id = r.id) AS job_count,
               (SELECT COUNT(*) FROM application
                 WHERE run_id = r.id AND status = 'applied') AS applied_count
          FROM run r
         ORDER BY r.created_at DESC, r.id DESC
        """
    ).fetchall()
    return templates.TemplateResponse(
        request, "review_run/list.html.j2", {"runs": [dict(r) for r in rows]}
    )


# ─── status validation helper ─────────────────────────────────────────


def validate_status_payload(payload: dict[str, Any]) -> list[str]:
    """Return a list of human-readable schema errors (empty = ok)."""
    errors = sorted(_STATUS_VALIDATOR.iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
