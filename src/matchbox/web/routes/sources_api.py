"""Sources JSON API (prefix /api/sources) for the React Sources screen.

Reuses the helpers + scan functions from the (Jinja) sources route -- only the
presentation differs. Scanning is real and live-fired; the visible-status pattern
means a bad slug shows up on the next scan.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.core.settings import set_setting
from matchbox.discovery.pollers import POLLERS
from matchbox.discovery.runner import scan_aggregators, scan_source
from matchbox.web.deps import ConnDep
from matchbox.web.routes.sources import _adzuna_config, _get_source, _list_sources

router = APIRouter(prefix="/api/sources")

ATS_TYPES = sorted(POLLERS.keys())


class SourceBody(BaseModel):
    ats_type: str
    slug: str
    company: str
    country: str | None = None
    sector: str | None = None


class AdzunaBody(BaseModel):
    app_id: str
    app_key: str
    country: str = "in"
    what: str = ""


@router.get("")
def sources(conn: ConnDep) -> dict[str, Any]:
    return {"sources": _list_sources(conn), "atsTypes": ATS_TYPES, "adzuna": _adzuna_config(conn)}


@router.post("")
def add_source(body: SourceBody, conn: ConnDep) -> dict[str, Any]:
    if body.ats_type not in POLLERS:
        raise HTTPException(status_code=400, detail=f"unsupported ATS type: {body.ats_type}")
    slug, company = body.slug.strip(), body.company.strip()
    if not slug or not company:
        raise HTTPException(status_code=400, detail="slug and company are required")
    try:
        cur = conn.execute(
            "INSERT INTO ats_source (ats_type, slug, company, country, sector) VALUES (?,?,?,?,?)",
            (body.ats_type, slug, company, body.country or None, body.sector or None),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409, detail=f"source already exists: {body.ats_type}/{slug}"
        ) from e
    return _get_source(conn, int(cur.lastrowid or 0))


@router.delete("/{source_id}")
def delete_source(source_id: int, conn: ConnDep) -> dict[str, str]:
    conn.execute("DELETE FROM ats_source WHERE id = ?", (source_id,))
    return {"ok": "true"}


@router.post("/{source_id}/toggle")
def toggle_source(source_id: int, conn: ConnDep) -> dict[str, Any]:
    src = _get_source(conn, source_id)
    conn.execute(
        "UPDATE ats_source SET enabled = ? WHERE id = ?", (0 if src["enabled"] else 1, source_id)
    )
    return _get_source(conn, source_id)


@router.post("/{source_id}/scan")
def scan_one(source_id: int, conn: ConnDep) -> dict[str, Any]:
    src = _get_source(conn, source_id)
    with httpx.Client() as client:
        result = scan_source(conn, src, client=client)
    return {"source": _get_source(conn, source_id), "result": result}


@router.post("/scan-remote")
def scan_remote(conn: ConnDep) -> dict[str, Any]:
    adzuna = _adzuna_config(conn)
    results = scan_aggregators(conn, adzuna=adzuna or None)
    return {
        "results": [
            {"name": r.name, "ok": r.ok, "inserted": r.inserted, "fetched": r.fetched, "error": r.error}
            for r in results
        ]
    }


@router.post("/adzuna")
def save_adzuna(body: AdzunaBody, conn: ConnDep) -> dict[str, Any]:
    cfg = {
        "app_id": body.app_id.strip(),
        "app_key": body.app_key.strip(),
        "queries": [{"country": (body.country.strip() or "in"), "what": body.what.strip()}],
    }
    set_setting(conn, "adzuna", json.dumps(cfg))
    return {"ok": "true"}
