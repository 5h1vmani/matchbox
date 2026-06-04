"""JSON API for the React tracker SPA.

Reads return the view-model directly (the repo serializes DB -> view-model);
mutations mirror the design's 8-action store contract, each returning the
updated application. Plus user listing/switching for the live profile switch.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from matchbox.core.db import connect, db_path, list_profiles
from matchbox.tracker import repo, service
from matchbox.web.deps import ACTIVE_PROFILE_COOKIE, ConnDep, ProfileDep

router = APIRouter(prefix="/api")


class StageBody(BaseModel):
    stage: str


class SnoozeBody(BaseModel):
    days: int = 2


class RemindBody(BaseModel):
    days: int


class ResponseBody(BaseModel):
    type: str


class NoteBody(BaseModel):
    text: str


class SwitchBody(BaseModel):
    slug: str


def _require(app: dict[str, Any] | None) -> dict[str, Any]:
    if app is None:
        raise HTTPException(status_code=404, detail="no such application")
    return app


# ── reads ─────────────────────────────────────────────────────────────────────


@router.get("/applications")
def list_applications(conn: ConnDep) -> list[dict[str, Any]]:
    return repo.load_apps(conn)


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
    return _require(service.set_stage(conn, app_id, body.stage))


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
    return _require(service.log_response(conn, app_id, body.type))


@router.post("/applications/{app_id}/note")
def add_note(app_id: int, body: NoteBody, conn: ConnDep) -> dict[str, Any]:
    return _require(service.add_note(conn, app_id, body.text))


@router.post("/applications/{app_id}/star")
def toggle_star(app_id: int, conn: ConnDep) -> dict[str, Any]:
    return _require(service.toggle_star(conn, app_id))
