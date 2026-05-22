"""Onboarding routes — file-drop staging into inbox/, paste box, and a
ready-to-paste prompt the user copies into Claude Code.

The actual parsing is the brain's job. The app only stages files.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from matchbox.core.db import PROJECT_ROOT
from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()

INBOX_DIR = PROJECT_ROOT / "inbox"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".json", ".html", ".rtf"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(name: str) -> str:
    """Strip path components and replace anything outside [A-Za-z0-9._-]."""
    leaf = Path(name).name
    safe = _SAFE_NAME.sub("_", leaf)
    return safe or "untitled"


def _staged_files() -> list[dict[str, object]]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for p in sorted(INBOX_DIR.iterdir()):
        if p.name.startswith("."):
            continue
        try:
            rel = str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            # Patched INBOX (tests) lives outside the project root.
            rel = f"inbox/{p.name}"
        rows.append({"name": p.name, "size": p.stat().st_size, "rel_path": rel})
    return rows


def profile_exists(conn: sqlite3.Connection) -> bool:
    """True if the user has any library state (profile row or experiences)."""
    has_profile = conn.execute("SELECT 1 FROM profile LIMIT 1").fetchone() is not None
    has_experiences = conn.execute("SELECT 1 FROM experience LIMIT 1").fetchone() is not None
    return has_profile or has_experiences


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_index(request: Request, conn: ConnDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "onboarding/index.html.j2",
        {
            "staged": _staged_files(),
            "has_profile": profile_exists(conn),
        },
    )


@router.post("/onboarding/upload", response_class=HTMLResponse)
async def upload_files(
    request: Request,
    files: Annotated[list[UploadFile], File(...)],
) -> HTMLResponse:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    for upload in files:
        if not upload.filename:
            continue
        ext = Path(upload.filename).suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(
                status_code=415, detail=f"file type not accepted: {ext or '<none>'}"
            )
        target = INBOX_DIR / _sanitize(upload.filename)
        written = 0
        with target.open("wb") as fh:
            while True:
                chunk = await upload.read(1024 * 64)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_SIZE:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"file too large: {upload.filename} > 25 MB",
                    )
                fh.write(chunk)
    return templates.TemplateResponse(
        request,
        "onboarding/_staged_list.html.j2",
        {"staged": _staged_files()},
    )


@router.post("/onboarding/paste", response_class=HTMLResponse)
def paste_notes(request: Request, text: str = Form(...)) -> HTMLResponse:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not text.strip():
        raise HTTPException(status_code=400, detail="paste was empty")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = INBOX_DIR / f"notes-{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return templates.TemplateResponse(
        request,
        "onboarding/_staged_list.html.j2",
        {"staged": _staged_files()},
    )


@router.delete("/onboarding/staged/{name}", response_class=Response)
def remove_staged(name: str) -> Response:
    safe = _sanitize(name)
    target = INBOX_DIR / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"no staged file: {safe}")
    try:
        target.resolve().relative_to(INBOX_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes inbox/") from e
    target.unlink()
    return Response(status_code=200)


@router.post("/onboarding/clear", response_class=HTMLResponse)
def clear_inbox(request: Request) -> HTMLResponse:
    if INBOX_DIR.exists():
        for p in INBOX_DIR.iterdir():
            if p.name.startswith("."):
                continue
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
    return templates.TemplateResponse(
        request,
        "onboarding/_staged_list.html.j2",
        {"staged": _staged_files()},
    )


@router.get("/onboarding/landing-redirect", include_in_schema=False)
def landing_redirect(conn: ConnDep) -> RedirectResponse:
    """Helper for the root route: pick the right landing page."""
    if profile_exists(conn):
        return RedirectResponse(url="/library", status_code=302)
    return RedirectResponse(url="/onboarding", status_code=302)
