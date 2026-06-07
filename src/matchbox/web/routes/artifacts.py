"""JSON API for artifact storage (prefix /api/applications).

GET  /api/applications/{application_id}/artifacts          -> list
GET  /api/applications/{application_id}/artifacts?kind=cv  -> filtered list
POST /api/applications/{application_id}/artifacts/{artifact_id}/status
     body: {"status": "sent"} -> updated artifact (404 if not found)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.artifacts import repo
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/applications")


class StatusBody(BaseModel):
    status: str


@router.get("/{application_id}/artifacts")
def list_artifacts(
    application_id: int,
    conn: ConnDep,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    """All artifacts for an application, ordered by id. Optionally filtered by kind."""
    return repo.list_for_app(conn, application_id, kind=kind)


@router.post("/{application_id}/artifacts/{artifact_id}/status")
def update_status(
    application_id: int,
    artifact_id: int,
    body: StatusBody,
    conn: ConnDep,
) -> dict[str, Any]:
    """Update the status of an artifact. 404 if the artifact does not exist."""
    try:
        updated = repo.set_status(conn, artifact_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="no such artifact")
    return updated
