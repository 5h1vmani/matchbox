"""Apply-packet API (prefix /api/applications).

Assembles the 4-tab packet view-model from the tailoring run artifacts (cv.pdf /
coverage.json / changes.md / cover.txt are served by the sandboxed
`/runs/<id>/output/...` route), saves + re-renders the cover, and submits the
application to `applied`. Questions come from the answer library (/api/answers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.core.db import PROJECT_ROOT
from matchbox.tracker import service
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/applications")

_RUNS_DIR = PROJECT_ROOT / "runs"


class CoverBody(BaseModel):
    text: str


def _out_dir(run_id: str, job_id: int) -> Path:
    return _RUNS_DIR / run_id / "output" / str(job_id)


def _file_url(run_id: str, job_id: int, name: str) -> str:
    return f"/runs/{run_id}/output/{job_id}/{name}"


def _app_row(conn: Any, app_id: int) -> Any:
    return conn.execute(
        "SELECT a.id, a.job_id, a.run_id, a.stage, j.company, j.title "
        "FROM application a JOIN job j ON j.id = a.job_id WHERE a.id = ?",
        (app_id,),
    ).fetchone()


@router.get("/{app_id}/packet")
def packet(app_id: int, conn: ConnDep) -> dict[str, Any]:
    """The packet view-model: résumé (cv.pdf + coverage + changes), cover, and the
    job context. Honest: a tab is null until its artifact actually exists."""
    row = _app_row(conn, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such application")
    run_id, job_id = row["run_id"], row["job_id"]

    resume: dict[str, Any] | None = None
    coverage: dict[str, Any] | None = None
    cover: dict[str, Any] = {"text": None, "coverUrl": None}

    if run_id:
        out = _out_dir(run_id, job_id)
        if (out / "cv.pdf").exists():
            resume = {
                "cvUrl": _file_url(run_id, job_id, "cv.pdf"),
                "changesUrl": _file_url(run_id, job_id, "changes.md")
                if (out / "changes.md").exists()
                else None,
            }
        cov_path = out / "coverage.json"
        if cov_path.exists():
            try:
                coverage = json.loads(cov_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                coverage = None
        cover_txt = out / "cover.txt"
        if cover_txt.exists():
            cover["text"] = cover_txt.read_text(encoding="utf-8")
        if (out / "cover.pdf").exists():
            cover["coverUrl"] = _file_url(run_id, job_id, "cover.pdf")

    return {
        "applicationId": row["id"],
        "jobId": job_id,
        "runId": run_id,
        "company": row["company"],
        "title": row["title"],
        "stage": row["stage"],
        "resume": resume,
        "coverage": coverage,
        "cover": cover,
    }


@router.post("/{app_id}/cover")
def save_cover(app_id: int, body: CoverBody, conn: ConnDep) -> dict[str, Any]:
    """Persist the cover body the user wrote/regenerated and re-render cover.pdf
    deterministically via assemble (the same renderer the manual path uses)."""
    row = _app_row(conn, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such application")
    run_id, job_id = row["run_id"], row["job_id"]
    if not run_id:
        raise HTTPException(status_code=409, detail="no tailoring run for this application")
    out = _out_dir(run_id, job_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cover.txt").write_text(body.text, encoding="utf-8")

    # Heavy import deferred to keep app startup light.
    from matchbox.assemble import _palette_and_font_for, assemble_cover

    palette, font = _palette_and_font_for(conn, run_id, job_id)
    try:
        assemble_cover(conn=conn, run_id=run_id, job_id=job_id, palette=palette, font=font)
    except FileNotFoundError as e:  # missing cover.txt should not happen (just wrote it)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"coverUrl": _file_url(run_id, job_id, "cover.pdf")}


@router.post("/{app_id}/submit")
def submit_application(app_id: int, conn: ConnDep) -> dict[str, Any]:
    """Submit: move the application to `applied` with applied_at + a +7d
    follow-up reminder (a due-date computed on read, not a scheduler)."""
    app = service.submit(conn, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="no such application")
    return app
