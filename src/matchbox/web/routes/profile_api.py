"""Profile JSON API (prefix /api) for the React Profile editor.

Reuses the helpers from the (Jinja) profile route -- only the presentation
differs. `/api/profile` already returns the sidebar chip; the editable profile
lives at `/api/profile/details`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from matchbox.web.deps import ConnDep
from matchbox.web.routes.profile import _load_profile, _split_links

router = APIRouter(prefix="/api/profile")


class ProfileBody(BaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    links: str = ""  # one per line or comma-separated


@router.get("/details")
def get_details(conn: ConnDep) -> dict[str, Any]:
    p = _load_profile(conn)
    return {
        "fullName": p.get("full_name") or "",
        "email": p.get("email") or "",
        "phone": p.get("phone") or "",
        "location": p.get("location") or "",
        "headline": p.get("headline") or "",
        "links": json.loads(p.get("links_json") or "[]"),
    }


@router.post("/details")
def save_details(body: ProfileBody, conn: ConnDep) -> dict[str, Any]:
    values = {
        "full_name": body.full_name.strip(),
        "email": (body.email or "").strip() or None,
        "phone": (body.phone or "").strip() or None,
        "location": (body.location or "").strip() or None,
        "headline": (body.headline or "").strip() or None,
        "links_json": json.dumps(_split_links(body.links or "")),
    }
    row = conn.execute("SELECT id FROM profile LIMIT 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO profile (full_name, email, phone, location, links_json, headline) "
            "VALUES (:full_name, :email, :phone, :location, :links_json, :headline)",
            values,
        )
    else:
        conn.execute(
            "UPDATE profile SET full_name=:full_name, email=:email, phone=:phone, "
            "location=:location, links_json=:links_json, headline=:headline WHERE id=:id",
            {**values, "id": row[0]},
        )
    return get_details(conn)
