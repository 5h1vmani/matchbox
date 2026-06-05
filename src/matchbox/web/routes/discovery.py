"""JSON API for the React Discovery SPA (prefix /api/discovery).

Reads return the `Role` / `WatchedCompany` view-model directly (discovery_api/repo
serializes DB -> view-model). The decision endpoints apply the effects in
discovery_api/service and return the updated role(s) plus, for `tailoring`, the
manual run hand-off so the UI can surface the "process run X" prompt.

Only scored jobs (those with a `score_breakdown_json`) enter discovery.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.discovery_api import repo, service
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/discovery")


class DecideBody(BaseModel):
    id: str
    decision: str


class BatchBody(BaseModel):
    ids: list[str]
    decision: str


def _job_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"bad job id: {raw!r}") from exc


# ── reads ─────────────────────────────────────────────────────────────────────


@router.get("/roles")
def list_roles(conn: ConnDep) -> list[dict[str, Any]]:
    """The full scored-role set (queue order applied; the SPA filters per surface)."""
    return repo.load_roles(conn)


@router.get("/roles/{job_id}")
def role_detail(job_id: int, conn: ConnDep) -> dict[str, Any]:
    """One role with its full JD. The list (/roles) trims the JD to its first
    paragraph; the JD drawer fetches the full text here when it opens."""
    role = repo.load_one(conn, job_id)
    if role is None:
        raise HTTPException(status_code=404, detail="no such role")
    return role


@router.get("/watchlist")
def watchlist(conn: ConnDep) -> list[dict[str, Any]]:
    return repo.load_watchlist(conn)


# ── decisions ──────────────────────────────────────────────────────────────────


@router.post("/decide")
def decide(body: DecideBody, conn: ConnDep) -> dict[str, Any]:
    if body.decision not in service.VALID_DECISIONS:
        raise HTTPException(status_code=400, detail=f"invalid decision: {body.decision!r}")
    return service.decide(conn, _job_id(body.id), body.decision)


@router.post("/batch")
def batch(body: BatchBody, conn: ConnDep) -> dict[str, Any]:
    if body.decision not in service.VALID_DECISIONS:
        raise HTTPException(status_code=400, detail=f"invalid decision: {body.decision!r}")
    ids = [_job_id(i) for i in body.ids]
    return service.batch_decide(conn, ids, body.decision)
