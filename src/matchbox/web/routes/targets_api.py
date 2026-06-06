"""Targets JSON API (prefix /api/targets) — the user's goals + work authorization.

One row in the `target` table. The React replacement for the Jinja targets page;
adds editing of `work_auth_json` (citizenships, needs_sponsorship, has_clearance),
which feeds the deterministic eligibility pre-filter in Discovery.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from matchbox.core.db import transaction
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/targets")


class WorkAuth(BaseModel):
    citizenships: list[str] = []
    needs_sponsorship: bool = False
    has_clearance: bool = False


class TargetsBody(BaseModel):
    role_families: list[str] = []
    dream_companies: list[str] = []
    locations: list[str] = []
    exclusions: list[str] = []
    work_auth: WorkAuth = WorkAuth()


def _load(conn: Any) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM target LIMIT 1").fetchone()
    if row is None:
        return {
            "role_families": [],
            "dream_companies": [],
            "locations": [],
            "exclusions": [],
            "work_auth": {"citizenships": [], "needs_sponsorship": False, "has_clearance": False},
        }
    wa = json.loads(row["work_auth_json"] or "{}")
    return {
        "role_families": json.loads(row["role_families_json"] or "[]"),
        "dream_companies": json.loads(row["dream_companies_json"] or "[]"),
        "locations": json.loads(row["locations_json"] or "[]"),
        "exclusions": json.loads(row["exclusions_json"] or "[]"),
        "work_auth": {
            "citizenships": wa.get("citizenships", []),
            "needs_sponsorship": bool(wa.get("needs_sponsorship", False)),
            "has_clearance": bool(wa.get("has_clearance", False)),
        },
    }


@router.get("")
def get_targets(conn: ConnDep) -> dict[str, Any]:
    return _load(conn)


@router.post("")
def save_targets(body: TargetsBody, conn: ConnDep) -> dict[str, Any]:
    values = {
        "role_families_json": json.dumps([s.strip() for s in body.role_families if s.strip()]),
        "dream_companies_json": json.dumps([s.strip() for s in body.dream_companies if s.strip()]),
        "locations_json": json.dumps([s.strip() for s in body.locations if s.strip()]),
        "exclusions_json": json.dumps([s.strip() for s in body.exclusions if s.strip()]),
        "work_auth_json": json.dumps(body.work_auth.model_dump()),
    }
    with transaction(conn):
        row = conn.execute("SELECT id FROM target LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO target (role_families_json, dream_companies_json, locations_json, "
                "comp_json, exclusions_json, work_auth_json) "
                "VALUES (:role_families_json, :dream_companies_json, :locations_json, '{}', "
                ":exclusions_json, :work_auth_json)",
                values,
            )
        else:
            conn.execute(
                "UPDATE target SET role_families_json=:role_families_json, "
                "dream_companies_json=:dream_companies_json, locations_json=:locations_json, "
                "exclusions_json=:exclusions_json, work_auth_json=:work_auth_json WHERE id=:id",
                {**values, "id": row[0]},
            )
    return _load(conn)
