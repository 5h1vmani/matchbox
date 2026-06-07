"""Targets — the user's goals (role families, dream companies, locations,
comp, exclusions). One row in the `target` table. Saved as JSON columns,
read back on render.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()


def _split_list(raw: str) -> list[str]:
    """Split a comma/newline-separated text area into a clean list."""
    parts = [p.strip() for chunk in raw.splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]


def _load_target(conn: ConnDep) -> dict[str, object]:
    row = conn.execute("SELECT * FROM target LIMIT 1").fetchone()
    if row is None:
        return {
            "role_families": [],
            "dream_companies": [],
            "locations": [],
            "comp": {},
            "exclusions": [],
        }
    return {
        "role_families": json.loads(row["role_families_json"]),
        "dream_companies": json.loads(row["dream_companies_json"]),
        "locations": json.loads(row["locations_json"]),
        "comp": json.loads(row["comp_json"]),
        "exclusions": json.loads(row["exclusions_json"]),
    }


@router.get("/targets", response_class=HTMLResponse)
def targets_form(request: Request, conn: ConnDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "onboarding/targets.html.j2",
        {"target": _load_target(conn)},
    )


@router.post("/targets", response_class=HTMLResponse)
def save_targets(
    request: Request,
    conn: ConnDep,
    role_families: str = Form(""),
    dream_companies: str = Form(""),
    locations: str = Form(""),
    comp_min: str = Form(""),
    comp_max: str = Form(""),
    comp_currency: str = Form("USD"),
    exclusions: str = Form(""),
) -> HTMLResponse:
    comp: dict[str, object] = {"currency": comp_currency.strip() or "USD"}
    if comp_min.strip():
        try:
            comp["min"] = int(comp_min)
        except ValueError:
            comp["min_raw"] = comp_min.strip()
    if comp_max.strip():
        try:
            comp["max"] = int(comp_max)
        except ValueError:
            comp["max_raw"] = comp_max.strip()

    values = {
        "role_families_json": json.dumps(_split_list(role_families)),
        "dream_companies_json": json.dumps(_split_list(dream_companies)),
        "locations_json": json.dumps(_split_list(locations)),
        "comp_json": json.dumps(comp),
        "exclusions_json": json.dumps(_split_list(exclusions)),
    }

    row = conn.execute("SELECT id FROM target LIMIT 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO target (role_families_json, dream_companies_json,
                                locations_json, comp_json, exclusions_json)
            VALUES (:role_families_json, :dream_companies_json,
                    :locations_json, :comp_json, :exclusions_json)
            """,
            values,
        )
    else:
        conn.execute(
            """
            UPDATE target SET role_families_json = :role_families_json,
                              dream_companies_json = :dream_companies_json,
                              locations_json = :locations_json,
                              comp_json = :comp_json,
                              exclusions_json = :exclusions_json
             WHERE id = :id
            """,
            {**values, "id": row[0]},
        )

    return templates.TemplateResponse(
        request,
        "onboarding/_targets_saved.html.j2",
        {"target": _load_target(conn)},
    )
