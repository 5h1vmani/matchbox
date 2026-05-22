"""Library routes — CRUD over experiences, bullets, projects, skills,
summary variants, and their tags.

GET returns full pages or list views. POST/PATCH/DELETE return HTML
fragments suitable for HTMX swap-in (or 200 with no body for deletes).
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from matchbox.core import library as lib
from matchbox.core.models import (
    Bullet,
    Facet,
    ItemType,
    Project,
    Skill,
    SummaryVariant,
    Tag,
    TaggedItem,
)
from matchbox.web.deps import get_conn
from matchbox.web.templates_env import templates

router = APIRouter()

ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]

VALID_FACETS: set[str] = {"role_family", "tech", "seniority", "impact"}
VALID_ITEM_TYPES: set[str] = {"bullet", "project", "skill", "summary_variant"}


def _facet(facet: str) -> Facet:
    if facet not in VALID_FACETS:
        raise HTTPException(status_code=400, detail=f"unknown facet: {facet}")
    return facet  # type: ignore[return-value]


def _item_type(item_type: str) -> ItemType:
    if item_type not in VALID_ITEM_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown item_type: {item_type}")
    return item_type  # type: ignore[return-value]


def _wrap_bullet(b: Bullet, tags: list[Tag] | None = None) -> TaggedItem:
    return TaggedItem(kind="bullet", item=b, tags=tags or [])


def _wrap_project(p: Project, tags: list[Tag] | None = None) -> TaggedItem:
    return TaggedItem(kind="project", item=p, tags=tags or [])


def _wrap_skill(s: Skill, tags: list[Tag] | None = None) -> TaggedItem:
    return TaggedItem(kind="skill", item=s, tags=tags or [])


def _wrap_summary(s: SummaryVariant, tags: list[Tag] | None = None) -> TaggedItem:
    return TaggedItem(kind="summary_variant", item=s, tags=tags or [])


# ─── library index page ───────────────────────────────────────────────


@router.get("/library", response_class=HTMLResponse)
def library_index(request: Request, conn: ConnDep) -> HTMLResponse:
    experiences = lib.list_experiences(conn)
    experience_blocks = [
        {
            "experience": e,
            "bullets": lib.bullets_with_tags(conn, experience_id=e.id),
        }
        for e in experiences
    ]
    return templates.TemplateResponse(
        request,
        "library/index.html.j2",
        {
            "experience_blocks": experience_blocks,
            "projects": lib.projects_with_tags(conn),
            "skills": lib.skills_with_tags(conn),
            "summaries": lib.summaries_with_tags(conn),
            "facets": sorted(VALID_FACETS),
        },
    )


# ─── experiences ──────────────────────────────────────────────────────


@router.post("/library/experiences", response_class=HTMLResponse)
def create_experience(
    request: Request,
    conn: ConnDep,
    company: str = Form(...),
    role: str = Form(...),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
    location: str | None = Form(None),
) -> HTMLResponse:
    exp = lib.add_experience(
        conn,
        company=company.strip(),
        role=role.strip(),
        start_date=(start_date or None),
        end_date=(end_date or None),
        location=(location or None),
    )
    return templates.TemplateResponse(
        request,
        "library/_experience_block.html.j2",
        {
            "block": {"experience": exp, "bullets": []},
            "facets": sorted(VALID_FACETS),
        },
    )


@router.delete("/library/experiences/{exp_id}", response_class=Response)
def delete_experience(exp_id: int, conn: ConnDep) -> Response:
    conn.execute("DELETE FROM experience WHERE id = ?", (exp_id,))
    return Response(status_code=200)


# ─── bullets ──────────────────────────────────────────────────────────


@router.post("/library/bullets", response_class=HTMLResponse)
def create_bullet(
    request: Request,
    conn: ConnDep,
    experience_id: int = Form(...),
    text: str = Form(...),
    has_metric: str | None = Form(None),
) -> HTMLResponse:
    bullet = lib.add_bullet(
        conn,
        experience_id=experience_id,
        text=text.strip(),
        has_metric=(has_metric == "on"),
    )
    return templates.TemplateResponse(
        request,
        "library/_bullet_row.html.j2",
        {"tagged": _wrap_bullet(bullet), "facets": sorted(VALID_FACETS)},
    )


@router.patch("/library/bullets/{bullet_id}", response_class=HTMLResponse)
def patch_bullet(
    request: Request,
    bullet_id: int,
    conn: ConnDep,
    text: str | None = Form(None),
    has_metric: str | None = Form(None),
    facts_verified: str | None = Form(None),
) -> HTMLResponse:
    lib.update_bullet(
        conn,
        bullet_id,
        text=text.strip() if text is not None else None,
        has_metric=(has_metric == "on") if has_metric is not None else None,
        facts_verified=(facts_verified == "on") if facts_verified is not None else None,
    )
    bullet = lib.get_bullet(conn, bullet_id)
    tags = lib.tags_for(conn, item_type="bullet", item_id=bullet_id)
    return templates.TemplateResponse(
        request,
        "library/_bullet_row.html.j2",
        {"tagged": _wrap_bullet(bullet, tags), "facets": sorted(VALID_FACETS)},
    )


@router.delete("/library/bullets/{bullet_id}", response_class=Response)
def delete_bullet(bullet_id: int, conn: ConnDep) -> Response:
    lib.delete_bullet(conn, bullet_id)
    return Response(status_code=200)


# ─── projects ─────────────────────────────────────────────────────────


@router.post("/library/projects", response_class=HTMLResponse)
def create_project(
    request: Request,
    conn: ConnDep,
    name: str = Form(...),
    text: str = Form(...),
    url: str | None = Form(None),
) -> HTMLResponse:
    p = lib.add_project(conn, name=name.strip(), text=text.strip(), url=(url or None))
    return templates.TemplateResponse(
        request,
        "library/_project_row.html.j2",
        {"tagged": _wrap_project(p), "facets": sorted(VALID_FACETS)},
    )


@router.delete("/library/projects/{project_id}", response_class=Response)
def delete_project(project_id: int, conn: ConnDep) -> Response:
    lib.delete_project(conn, project_id)
    return Response(status_code=200)


# ─── skills ───────────────────────────────────────────────────────────


@router.post("/library/skills", response_class=HTMLResponse)
def create_skill(
    request: Request,
    conn: ConnDep,
    name: str = Form(...),
    category: str | None = Form(None),
    proficiency: str | None = Form(None),
) -> HTMLResponse:
    prof: Literal["working", "fluent", "expert"] | None = None
    if proficiency in ("working", "fluent", "expert"):
        prof = proficiency  # type: ignore[assignment]
    try:
        s = lib.add_skill(conn, name=name.strip(), category=(category or None), proficiency=prof)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"skill already exists: {name}") from e
    return templates.TemplateResponse(
        request,
        "library/_skill_row.html.j2",
        {"tagged": _wrap_skill(s), "facets": sorted(VALID_FACETS)},
    )


@router.delete("/library/skills/{skill_id}", response_class=Response)
def delete_skill(skill_id: int, conn: ConnDep) -> Response:
    lib.delete_skill(conn, skill_id)
    return Response(status_code=200)


# ─── summary variants ─────────────────────────────────────────────────


@router.post("/library/summaries", response_class=HTMLResponse)
def create_summary(
    request: Request,
    conn: ConnDep,
    label: str = Form(...),
    text: str = Form(...),
) -> HTMLResponse:
    sm = lib.add_summary(conn, label=label.strip(), text=text.strip())
    return templates.TemplateResponse(
        request,
        "library/_summary_row.html.j2",
        {"tagged": _wrap_summary(sm), "facets": sorted(VALID_FACETS)},
    )


@router.delete("/library/summaries/{summary_id}", response_class=Response)
def delete_summary(summary_id: int, conn: ConnDep) -> Response:
    lib.delete_summary(conn, summary_id)
    return Response(status_code=200)


# ─── tags (polymorphic) ───────────────────────────────────────────────


@router.post("/library/tags/{item_type}/{item_id}", response_class=HTMLResponse)
def attach_tag(
    request: Request,
    item_type: str,
    item_id: int,
    conn: ConnDep,
    facet: str = Form(...),
    value: str = Form(...),
) -> HTMLResponse:
    typed_item = _item_type(item_type)
    typed_facet = _facet(facet)
    tag = lib.attach_tag(
        conn,
        item_type=typed_item,
        item_id=item_id,
        facet=typed_facet,
        value=value.strip(),
    )
    return templates.TemplateResponse(
        request,
        "library/_tag_chip.html.j2",
        {"tag": tag, "item_type": typed_item, "item_id": item_id},
    )


@router.delete("/library/tags/{item_type}/{item_id}/{tag_id}", response_class=Response)
def detach_tag(item_type: str, item_id: int, tag_id: int, conn: ConnDep) -> Response:
    typed_item = _item_type(item_type)
    lib.detach_tag(conn, item_type=typed_item, item_id=item_id, tag_id=tag_id)
    return Response(status_code=200)
