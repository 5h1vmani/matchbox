"""Onboarding JSON API (prefix /api/onboarding) for the React Intake screen.

Reuses the file-staging helpers from the (Jinja) onboarding route -- only the
presentation differs. The app stages files into inbox/; the actual parsing is the
brain's job (the user runs "ingest my files" in Claude Code). Honest copy in the
UI says exactly that.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from matchbox.web.deps import ConnDep
from matchbox.web.routes import onboarding
from matchbox.web.routes.onboarding import (
    ALLOWED_EXTS,
    MAX_FILE_SIZE,
    _sanitize,
    _staged_files,
    profile_exists,
)

router = APIRouter(prefix="/api/onboarding")


@router.get("")
def onboarding_state(conn: ConnDep) -> dict[str, Any]:
    return {"staged": _staged_files(), "hasProfile": profile_exists(conn)}


@router.get("/staged")
def staged() -> list[dict[str, object]]:
    return _staged_files()


@router.post("/upload")
async def upload(files: Annotated[list[UploadFile], File(...)]) -> list[dict[str, object]]:
    onboarding.INBOX_DIR.mkdir(parents=True, exist_ok=True)
    for upload_file in files:
        if not upload_file.filename:
            continue
        ext = Path(upload_file.filename).suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(status_code=415, detail=f"file type not accepted: {ext or '<none>'}")
        target = onboarding.INBOX_DIR / _sanitize(upload_file.filename)
        written = 0
        with target.open("wb") as fh:
            while True:
                chunk = await upload_file.read(1024 * 64)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_SIZE:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413, detail=f"file too large: {upload_file.filename} > 25 MB"
                    )
                fh.write(chunk)
    return _staged_files()


@router.post("/paste")
def paste(text: Annotated[str, Form()]) -> list[dict[str, object]]:
    onboarding.INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not text.strip():
        raise HTTPException(status_code=400, detail="paste was empty")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (onboarding.INBOX_DIR / f"notes-{stamp}.md").write_text(text, encoding="utf-8")
    return _staged_files()


@router.delete("/staged/{name}")
def remove_staged(name: str) -> dict[str, str]:
    target = onboarding.INBOX_DIR / _sanitize(name)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"no staged file: {name}")
    try:
        target.resolve().relative_to(onboarding.INBOX_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes inbox/") from e
    target.unlink()
    return {"ok": "true"}
