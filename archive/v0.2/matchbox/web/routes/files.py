"""Secure file serving — generated PDFs only, scoped to job's output dir.

Path traversal is blocked at two layers: the filename pattern in the route,
and `safe_output_path` which verifies the resolved path stays under the job's
output directory.
"""

from __future__ import annotations

from fastapi import APIRouter, Path
from fastapi.responses import FileResponse

from matchbox.web.deps import ProfileDep, SettingsDep, safe_output_path

router = APIRouter()


@router.get("/{job_id}/{filename}")
async def serve_file(
    settings: SettingsDep,
    profile: ProfileDep,
    job_id: int,
    filename: str = Path(..., pattern=r"^[a-zA-Z0-9._-]+\.(pdf|png)$"),
) -> FileResponse:
    path = safe_output_path(settings, profile, job_id, filename)
    media = "application/pdf" if filename.endswith(".pdf") else "image/png"
    return FileResponse(path, media_type=media, filename=filename)
