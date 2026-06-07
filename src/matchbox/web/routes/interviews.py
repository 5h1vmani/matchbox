"""JSON API for the interview loop (rounds + debriefs).

Powers the Workspace timeline. Rounds are manual entry (no calendar/ATS sync);
the debrief is a one-tap honest capture shown side-by-side with outcomes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.interviews import repo
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api")


class RoundCreateBody(BaseModel):
    kind: str
    scheduledAt: str | None = None
    focus: str | None = None
    status: str = "scheduled"


class RoundUpdateBody(BaseModel):
    kind: str | None = None
    scheduledAt: str | None = None
    focus: str | None = None
    status: str | None = None


class DebriefBody(BaseModel):
    sentiment: str | None = None
    notes: str | None = None


def _require(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail="no such round")
    return row


@router.get("/applications/{app_id}/rounds")
def list_rounds(app_id: int, conn: ConnDep) -> list[dict[str, Any]]:
    return repo.rounds_for(conn, app_id)


@router.post("/applications/{app_id}/rounds")
def create_round(app_id: int, body: RoundCreateBody, conn: ConnDep) -> dict[str, Any]:
    try:
        rid = repo.create_round(
            conn,
            app_id,
            kind=body.kind,
            scheduled_at=body.scheduledAt,
            focus=body.focus,
            status=body.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _require(repo.get_round(conn, rid))


@router.patch("/rounds/{round_id}")
def update_round(round_id: int, body: RoundUpdateBody, conn: ConnDep) -> dict[str, Any]:
    try:
        return _require(
            repo.update_round(
                conn,
                round_id,
                kind=body.kind,
                scheduled_at=body.scheduledAt,
                focus=body.focus,
                status=body.status,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/rounds/{round_id}/debrief")
def capture_debrief(round_id: int, body: DebriefBody, conn: ConnDep) -> dict[str, Any]:
    if repo.get_round(conn, round_id) is None:
        raise HTTPException(status_code=404, detail="no such round")
    try:
        return _require(
            repo.upsert_debrief(conn, round_id, sentiment=body.sentiment, notes=body.notes)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/rounds/{round_id}")
def delete_round(round_id: int, conn: ConnDep) -> dict[str, str]:
    repo.delete_round(conn, round_id)
    return {"ok": "true"}
