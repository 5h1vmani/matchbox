"""Profile editor — name, email, phone, location, links, headline.

After onboarding writes a row via ingest, the user needs a way to fix
typos or add a missed field without touching the DB. The profile is the
top of every rendered CV, so this matters.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()


def _load_profile(conn: ConnDep) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profile LIMIT 1").fetchone()
    if row is None:
        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "links_json": "[]",
            "headline": "",
        }
    return dict(row)


def _split_links(raw: str) -> list[str]:
    """One link per line, or comma-separated. Strip whitespace, drop empties."""
    parts = [p.strip() for chunk in raw.splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]


@router.get("/profile", response_class=HTMLResponse)
def profile_form(request: Request, conn: ConnDep) -> HTMLResponse:
    profile = _load_profile(conn)
    profile["links"] = json.loads(profile.get("links_json") or "[]")
    return templates.TemplateResponse(
        request,
        "profile/index.html.j2",
        {"profile": profile},
    )


@router.post("/profile", response_class=HTMLResponse)
def save_profile(
    request: Request,
    conn: ConnDep,
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    headline: Annotated[str, Form()] = "",
    links: Annotated[str, Form()] = "",
) -> HTMLResponse:
    values = {
        "full_name": full_name.strip(),
        "email": (email or "").strip() or None,
        "phone": (phone or "").strip() or None,
        "location": (location or "").strip() or None,
        "headline": (headline or "").strip() or None,
        "links_json": json.dumps(_split_links(links or "")),
    }
    row = conn.execute("SELECT id FROM profile LIMIT 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO profile (full_name, email, phone, location, links_json, headline)
            VALUES (:full_name, :email, :phone, :location, :links_json, :headline)
            """,
            values,
        )
    else:
        conn.execute(
            """
            UPDATE profile
               SET full_name = :full_name, email = :email, phone = :phone,
                   location = :location, links_json = :links_json, headline = :headline
             WHERE id = :id
            """,
            {**values, "id": row[0]},
        )
    return templates.TemplateResponse(
        request,
        "profile/_saved.html.j2",
        {},
    )
