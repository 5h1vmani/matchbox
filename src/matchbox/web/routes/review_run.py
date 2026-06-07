"""Run artifacts: sandboxed file serving + run deletion + status validation.

The Jinja review-run progress UI has been archived (the React app uses the run
handoff toast + the Apply packet instead). What remains here is the
non-presentational core: the sandboxed `/runs/<id>/output/...` file route the
Apply packet reads (cv.pdf / coverage.json / changes.md / cover.pdf), run
deletion, and the status.json schema validation.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from jsonschema import Draft202012Validator

from matchbox.core.db import PROJECT_ROOT
from matchbox.web.deps import ConnDep

router = APIRouter()

RUNS_DIR = PROJECT_ROOT / "runs"
STATUS_SCHEMA = json.loads(
    (PROJECT_ROOT / "schemas" / "status.v1.json").read_text(encoding="utf-8")
)
_STATUS_VALIDATOR = Draft202012Validator(STATUS_SCHEMA)


def validate_status_payload(payload: dict[str, Any]) -> list[str]:
    """Return a list of human-readable schema errors (empty = ok)."""
    errors = sorted(_STATUS_VALIDATOR.iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


@router.delete("/runs/{run_id}", response_class=Response)
def delete_run(run_id: str, conn: ConnDep) -> Response:
    """Delete a run row, its run_job links, its application rows, and its
    runs/<id>/ directory on disk.

    The job rows themselves stay -- those came from ATS scans and belong to the
    inbox. Their status is reset to 'scored' so the user can re-queue them.
    """
    row = conn.execute("SELECT 1 FROM run WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id}")
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

    # Tear down the on-disk artifacts. Refuse to follow a symlink as the run dir.
    run_dir = (RUNS_DIR / run_id).resolve()
    try:
        run_dir.relative_to(RUNS_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="run id escapes runs/") from e
    if run_dir.exists() and run_dir.is_dir():
        shutil.rmtree(run_dir)
    return Response(status_code=200)


@router.get("/runs/{run_id}/output/{job_id}/{filename}", include_in_schema=False)
def serve_run_file(run_id: str, job_id: int, filename: str) -> FileResponse:
    """Serve a file from runs/<run_id>/output/<job_id>/ only. Path traversal is
    rejected by .resolve() + .relative_to() check. This is the route the Apply
    packet reads cv.pdf / coverage.json / changes.md / cover.pdf through."""
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
