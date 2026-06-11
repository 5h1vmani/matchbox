"""JSON API for the React tracker SPA.

Reads return the view-model directly (the repo serializes DB -> view-model);
mutations mirror the design's 8-action store contract, each returning the
updated application. Plus user listing/switching for the live profile switch.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from matchbox.core.db import PROJECT_ROOT, connect, db_path, list_profiles
from matchbox.core.migrations import migrate
from matchbox.doctor import checks as doctor_checks
from matchbox.tracker import repo, service
from matchbox.web.deps import ACTIVE_PROFILE_COOKIE, ConnDep, ProfileDep

router = APIRouter(prefix="/api")


class StageBody(BaseModel):
    stage: str
    closeReason: str | None = None


class SnoozeBody(BaseModel):
    days: int = 2


class RemindBody(BaseModel):
    days: int


class ResponseBody(BaseModel):
    type: str
    closeReason: str | None = None


class NoteBody(BaseModel):
    text: str


class SwitchBody(BaseModel):
    slug: str


class CreateUserBody(BaseModel):
    name: str


def _require(app: dict[str, Any] | None) -> dict[str, Any]:
    if app is None:
        raise HTTPException(status_code=404, detail="no such application")
    return app


# ── reads ─────────────────────────────────────────────────────────────────────


@router.get("/doctor")
def doctor() -> dict[str, Any]:
    """The matchbox-doctor checks as JSON, so the UI can show real environment
    status (e.g. whether the claude CLI is on PATH) instead of guessing."""
    return {"checks": [asdict(check) for check in doctor_checks()]}


@router.get("/applications")
def list_applications(conn: ConnDep) -> list[dict[str, Any]]:
    return repo.load_apps(conn)


@router.get("/applications/{app_id}/cv", include_in_schema=False)
def serve_cv(app_id: int, conn: ConnDep) -> FileResponse:
    """Serve the application's tailored CV PDF. The stored cv_path is
    repo-relative (e.g. people/<slug>/output/<job>/cv.pdf); refuse anything
    that resolves outside the project root or is not a PDF."""
    row = conn.execute("SELECT cv_path FROM application WHERE id=?", (app_id,)).fetchone()
    if row is None or not row["cv_path"]:
        raise HTTPException(status_code=404, detail="no CV for this application")
    target = (PROJECT_ROOT / row["cv_path"]).resolve()
    try:
        target.relative_to(PROJECT_ROOT.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="cv path escapes project root") from e
    if target.suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail=f"refused type: {target.suffix}")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="CV file missing on disk")
    return FileResponse(str(target), media_type="application/pdf")


@router.get("/profile")
def get_profile(conn: ConnDep, profile: ProfileDep) -> dict[str, str]:
    row = conn.execute("SELECT full_name FROM profile LIMIT 1").fetchone()
    name = (row["full_name"] if row else None) or profile
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    return {"name": name, "initials": initials, "slug": profile}


# ── users (live profile switch) ────────────────────────────────────────────────


@router.get("/users")
def users(profile: ProfileDep) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for slug in list_profiles():
        name = slug
        conn = connect(db_path(slug))
        try:
            row = conn.execute("SELECT full_name FROM profile LIMIT 1").fetchone()
            if row and row["full_name"]:
                name = row["full_name"]
        except Exception:
            pass
        finally:
            conn.close()
        out.append({"slug": slug, "name": name, "active": slug == profile})
    return out


@router.post("/users")
def create_user(body: CreateUserBody, response: Response) -> dict[str, str]:
    """Create a fresh profile DB at people/<slug>/ and make it active."""
    name = body.name.strip()
    if name.startswith("_"):
        raise HTTPException(status_code=400, detail="profile names may not start with '_'")
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-")).strip("-")
    if not slug:
        raise HTTPException(status_code=400, detail="that name does not make a usable profile")
    if slug == "demo":
        raise HTTPException(status_code=400, detail="'demo' is the reserved sample profile")
    if slug in set(list_profiles()):
        raise HTTPException(status_code=409, detail=f"profile '{slug}' already exists")
    conn = connect(db_path(slug))  # connect() mkdirs people/<slug>/
    try:
        migrate(conn)
    finally:
        conn.close()
    response.set_cookie(
        ACTIVE_PROFILE_COOKIE,
        slug,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    return {"slug": slug}


@router.post("/users/switch")
def switch_user(body: SwitchBody, response: Response) -> dict[str, Any]:
    if body.slug not in set(list_profiles()):
        raise HTTPException(status_code=400, detail="unknown profile")
    response.set_cookie(
        ACTIVE_PROFILE_COOKIE,
        body.slug,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    return {"ok": True, "slug": body.slug}


# ── mutations (the 8-action store contract) ────────────────────────────────────


@router.post("/applications/{app_id}/advance")
def advance(app_id: int, conn: ConnDep) -> dict[str, Any]:
    return _require(service.advance_stage(conn, app_id))


@router.post("/applications/{app_id}/stage")
def set_stage(app_id: int, body: StageBody, conn: ConnDep) -> dict[str, Any]:
    return _require(service.set_stage(conn, app_id, body.stage, body.closeReason))


@router.post("/applications/{app_id}/snooze")
def snooze(app_id: int, body: SnoozeBody, conn: ConnDep) -> dict[str, Any]:
    return _require(service.snooze(conn, app_id, body.days))


@router.post("/applications/{app_id}/remind")
def remind(app_id: int, body: RemindBody, conn: ConnDep) -> dict[str, Any]:
    return _require(service.remind(conn, app_id, body.days))


@router.post("/applications/{app_id}/done")
def mark_done(app_id: int, conn: ConnDep) -> dict[str, Any]:
    return _require(service.mark_done(conn, app_id))


@router.post("/applications/{app_id}/response")
def log_response(app_id: int, body: ResponseBody, conn: ConnDep) -> dict[str, Any]:
    if body.type not in ("reply", "rejected", "ghosted"):
        raise HTTPException(status_code=400, detail="invalid response type")
    return _require(service.log_response(conn, app_id, body.type, body.closeReason))


@router.post("/applications/{app_id}/note")
def add_note(app_id: int, body: NoteBody, conn: ConnDep) -> dict[str, Any]:
    return _require(service.add_note(conn, app_id, body.text))


@router.post("/applications/{app_id}/star")
def toggle_star(app_id: int, conn: ConnDep) -> dict[str, Any]:
    return _require(service.toggle_star(conn, app_id))
