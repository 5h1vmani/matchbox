"""Sources — add, list, enable/disable, delete ATS sources, and run scans.

The add-source flow probes the slug once before saving so the user is not
left with a phantom source that always errors.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from matchbox.core.settings import get_setting, set_setting
from matchbox.discovery.base import PollerError
from matchbox.discovery.pollers import POLLERS
from matchbox.discovery.runner import scan_aggregators, scan_all, scan_source
from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()

ATS_TYPES = sorted(POLLERS.keys())


def _list_sources(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM job j WHERE j.source = s.id) AS job_count
          FROM ats_source s
         ORDER BY s.company, s.slug
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _get_source(conn: sqlite3.Connection, source_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM ats_source WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no such source: {source_id}")
    return dict(row)


def _adzuna_config(conn: sqlite3.Connection) -> dict[str, Any]:
    """The user's Adzuna BYO-key config, stored in `setting`. Empty if unset."""
    value = get_setting(conn, "adzuna")
    if value is None:
        return {}
    try:
        cfg = json.loads(value)
    except (ValueError, TypeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


@router.get("/sources", response_class=HTMLResponse)
def sources_index(request: Request, conn: ConnDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sources/index.html.j2",
        {
            "sources": _list_sources(conn),
            "ats_types": ATS_TYPES,
            "adzuna": _adzuna_config(conn),
        },
    )


@router.post("/sources", response_class=HTMLResponse)
def add_source(
    request: Request,
    conn: ConnDep,
    ats_type: str = Form(...),
    slug: str = Form(...),
    company: str = Form(...),
    country: str | None = Form(None),
    sector: str | None = Form(None),
) -> HTMLResponse:
    if ats_type not in POLLERS:
        raise HTTPException(status_code=400, detail=f"unsupported ATS type: {ats_type}")
    slug_clean = slug.strip()
    company_clean = company.strip()
    if not slug_clean or not company_clean:
        raise HTTPException(status_code=400, detail="slug and company are required")

    # Insert (or fail on uniqueness conflict) first; running a real probe
    # here would add latency to every add. The visible-status pattern means
    # the next scan reveals whether the slug works.
    try:
        cur = conn.execute(
            """
            INSERT INTO ats_source (ats_type, slug, company, country, sector)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ats_type, slug_clean, company_clean, country or None, sector or None),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409, detail=f"source already exists: {ats_type}/{slug_clean}"
        ) from e
    src_id = cur.lastrowid
    assert src_id is not None
    return templates.TemplateResponse(
        request,
        "sources/_row.html.j2",
        {"source": _get_source(conn, src_id)},
    )


@router.delete("/sources/{source_id}", response_class=Response)
def delete_source(source_id: int, conn: ConnDep) -> Response:
    # Setting the FK to SET NULL on delete preserves existing jobs.
    conn.execute("DELETE FROM ats_source WHERE id = ?", (source_id,))
    return Response(status_code=200)


@router.post("/sources/{source_id}/toggle", response_class=HTMLResponse)
def toggle_source(request: Request, source_id: int, conn: ConnDep) -> HTMLResponse:
    src = _get_source(conn, source_id)
    conn.execute(
        "UPDATE ats_source SET enabled = ? WHERE id = ?",
        (0 if src["enabled"] else 1, source_id),
    )
    return templates.TemplateResponse(
        request, "sources/_row.html.j2", {"source": _get_source(conn, source_id)}
    )


@router.post("/sources/{source_id}/scan", response_class=HTMLResponse)
def scan_one(request: Request, source_id: int, conn: ConnDep) -> HTMLResponse:
    src = _get_source(conn, source_id)
    import httpx

    with httpx.Client() as client:
        result = scan_source(conn, src, client=client)
    return templates.TemplateResponse(
        request,
        "sources/_row.html.j2",
        {"source": _get_source(conn, source_id), "last_result": result},
    )


@router.post("/sources/scan-all", response_class=HTMLResponse)
def scan_all_route(request: Request, conn: ConnDep) -> HTMLResponse:
    results = scan_all(conn)
    return templates.TemplateResponse(
        request,
        "sources/_scan_summary.html.j2",
        {
            "results": results,
            "total_inserted": sum(r.inserted for r in results),
            "ok_count": sum(1 for r in results if r.ok),
            "fail_count": sum(1 for r in results if not r.ok),
        },
    )


@router.post("/sources/adzuna", response_class=HTMLResponse)
def save_adzuna(
    request: Request,
    conn: ConnDep,
    app_id: str = Form(""),
    app_key: str = Form(""),
    country: str = Form("in"),
    what: str = Form(""),
) -> HTMLResponse:
    """Save the user's Adzuna BYO key + default query in `setting`."""
    cfg = {
        "app_id": app_id.strip(),
        "app_key": app_key.strip(),
        "queries": [{"country": (country.strip() or "in"), "what": what.strip()}],
    }
    set_setting(conn, "adzuna", json.dumps(cfg))
    return HTMLResponse('<span class="text-success">Adzuna settings saved.</span>')


@router.post("/sources/scan-remote", response_class=HTMLResponse)
def scan_remote_route(request: Request, conn: ConnDep) -> HTMLResponse:
    """Scan the no-auth remote aggregators (Himalayas + Remotive), plus Adzuna
    if a BYO key is configured. Jobs land with source = NULL, tagged remote."""
    adzuna = _adzuna_config(conn)
    results = scan_aggregators(conn, himalayas=True, remotive=True, adzuna=adzuna or None)
    total = sum(r.inserted for r in results)
    parts = "; ".join(
        f"{r.name} +{r.inserted}" if r.ok else f"{r.name} error: {r.error}" for r in results
    )
    return HTMLResponse(
        f'<div id="remote-scan-summary" class="text-xs">'
        f'<div class="text-success">added {total} remote/aggregator jobs</div>'
        f'<div class="text-text-muted">{parts}</div></div>'
    )


@router.post("/sources/probe", response_class=HTMLResponse)
def probe_route(
    request: Request,
    ats_type: str = Form(...),
    slug: str = Form(...),
    company: str = Form(""),
) -> HTMLResponse:
    """Probe a slug without saving — used by the add form to surface a
    real error before the user commits."""
    if ats_type not in POLLERS:
        raise HTTPException(status_code=400, detail=f"unsupported ATS type: {ats_type}")
    import httpx

    try:
        with httpx.Client() as client:
            rows = POLLERS[ats_type](slug.strip(), company.strip() or slug.strip(), client)
    except PollerError as e:
        return templates.TemplateResponse(
            request,
            "sources/_probe_result.html.j2",
            {"ok": False, "error": e.message, "count": 0},
        )
    return templates.TemplateResponse(
        request,
        "sources/_probe_result.html.j2",
        {"ok": True, "error": None, "count": len(rows)},
    )
