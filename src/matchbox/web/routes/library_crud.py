"""JSON library CRUD (prefix /api/library) for the React Library editor.

The HTML library router renders HTMX fragments; this exposes the same `core.library`
DAL operations as JSON so the SPA owns the editor. SSOT: every write still goes
through the one library DAL.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.core import library as lib
from matchbox.core.models import Bullet, Project, Skill, SummaryVariant, Tag
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/library")

VALID_FACETS = {"role_family", "tech", "seniority", "impact"}
VALID_ITEM_TYPES = {"bullet", "project", "skill", "summary_variant"}


def _tags(conn: Any, item_type: str, item_id: int) -> list[dict[str, Any]]:
    return [
        {"id": t.id, "facet": t.facet, "value": t.value}
        for t in lib.tags_for(conn, item_type=item_type, item_id=item_id)  # type: ignore[arg-type]
    ]


def _bullet(conn: Any, b: Bullet) -> dict[str, Any]:
    return {
        "id": b.id,
        "experienceId": b.experience_id,
        "text": b.text,
        "hasMetric": b.has_metric,
        "verified": b.facts_verified,
        "tags": _tags(conn, "bullet", b.id),
    }


class ExperienceBody(BaseModel):
    company: str
    role: str
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None


class BulletBody(BaseModel):
    experience_id: int
    text: str
    has_metric: bool = False


class BulletPatch(BaseModel):
    text: str | None = None
    has_metric: bool | None = None
    facts_verified: bool | None = None


class ProjectBody(BaseModel):
    name: str
    text: str
    url: str | None = None


class SkillBody(BaseModel):
    name: str
    category: str | None = None
    proficiency: Literal["working", "fluent", "expert"] | None = None


class SummaryBody(BaseModel):
    label: str
    text: str


class TagBody(BaseModel):
    facet: str
    value: str


@router.get("")
def library(conn: ConnDep) -> dict[str, Any]:
    experiences = []
    for e in lib.list_experiences(conn):
        bullets = [
            _bullet(conn, b.item)  # type: ignore[arg-type]
            for b in lib.bullets_with_tags(conn, experience_id=e.id)
        ]
        experiences.append(
            {
                "id": e.id,
                "company": e.company,
                "role": e.role,
                "startDate": e.start_date,
                "endDate": e.end_date,
                "location": e.location,
                "bullets": bullets,
            }
        )

    def _proj(p: Project) -> dict[str, Any]:
        return {"id": p.id, "name": p.name, "text": p.text, "url": p.url, "verified": p.facts_verified,
                "tags": _tags(conn, "project", p.id)}

    def _skill(s: Skill) -> dict[str, Any]:
        return {"id": s.id, "name": s.name, "category": s.category, "proficiency": s.proficiency}

    def _summary(s: SummaryVariant) -> dict[str, Any]:
        return {"id": s.id, "label": s.label, "text": s.text}

    return {
        "experiences": experiences,
        "projects": [_proj(p) for p in lib.list_projects(conn)],
        "skills": [_skill(s) for s in lib.list_skills(conn)],
        "summaries": [_summary(s) for s in lib.list_summaries(conn)],
    }


@router.post("/experiences")
def add_experience(body: ExperienceBody, conn: ConnDep) -> dict[str, Any]:
    e = lib.add_experience(
        conn, company=body.company.strip(), role=body.role.strip(),
        start_date=body.start_date, end_date=body.end_date, location=body.location,
    )
    return {"id": e.id, "company": e.company, "role": e.role, "startDate": e.start_date,
            "endDate": e.end_date, "location": e.location, "bullets": []}


@router.delete("/experiences/{exp_id}")
def delete_experience(exp_id: int, conn: ConnDep) -> dict[str, str]:
    conn.execute("DELETE FROM experience WHERE id = ?", (exp_id,))
    return {"ok": "true"}


@router.post("/bullets")
def add_bullet(body: BulletBody, conn: ConnDep) -> dict[str, Any]:
    b = lib.add_bullet(conn, experience_id=body.experience_id, text=body.text.strip(),
                       has_metric=body.has_metric)
    return _bullet(conn, b)


@router.patch("/bullets/{bullet_id}")
def patch_bullet(bullet_id: int, body: BulletPatch, conn: ConnDep) -> dict[str, Any]:
    b = lib.update_bullet(conn, bullet_id, text=body.text, has_metric=body.has_metric,
                          facts_verified=body.facts_verified)
    return _bullet(conn, b)


@router.delete("/bullets/{bullet_id}")
def delete_bullet(bullet_id: int, conn: ConnDep) -> dict[str, str]:
    lib.delete_bullet(conn, bullet_id)
    return {"ok": "true"}


@router.post("/projects")
def add_project(body: ProjectBody, conn: ConnDep) -> dict[str, Any]:
    p = lib.add_project(conn, name=body.name.strip(), text=body.text.strip(), url=body.url)
    return {"id": p.id, "name": p.name, "text": p.text, "url": p.url, "verified": p.facts_verified, "tags": []}


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, conn: ConnDep) -> dict[str, str]:
    lib.delete_project(conn, project_id)
    return {"ok": "true"}


@router.post("/skills")
def add_skill(body: SkillBody, conn: ConnDep) -> dict[str, Any]:
    import sqlite3

    try:
        s = lib.add_skill(conn, name=body.name.strip(), category=body.category, proficiency=body.proficiency)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"skill already exists: {body.name}") from e
    return {"id": s.id, "name": s.name, "category": s.category, "proficiency": s.proficiency}


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int, conn: ConnDep) -> dict[str, str]:
    lib.delete_skill(conn, skill_id)
    return {"ok": "true"}


@router.post("/summaries")
def add_summary(body: SummaryBody, conn: ConnDep) -> dict[str, Any]:
    s = lib.add_summary(conn, label=body.label.strip(), text=body.text.strip())
    return {"id": s.id, "label": s.label, "text": s.text}


@router.delete("/summaries/{summary_id}")
def delete_summary(summary_id: int, conn: ConnDep) -> dict[str, str]:
    lib.delete_summary(conn, summary_id)
    return {"ok": "true"}


@router.post("/tags/{item_type}/{item_id}")
def attach_tag(item_type: str, item_id: int, body: TagBody, conn: ConnDep) -> dict[str, Any]:
    if item_type not in VALID_ITEM_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown item_type: {item_type}")
    if body.facet not in VALID_FACETS:
        raise HTTPException(status_code=400, detail=f"unknown facet: {body.facet}")
    t: Tag = lib.attach_tag(
        conn, item_type=item_type, item_id=item_id,  # type: ignore[arg-type]
        facet=body.facet, value=body.value.strip(),  # type: ignore[arg-type]
    )
    return {"id": t.id, "facet": t.facet, "value": t.value}


@router.delete("/tags/{item_type}/{item_id}/{tag_id}")
def detach_tag(item_type: str, item_id: int, tag_id: int, conn: ConnDep) -> dict[str, str]:
    if item_type not in VALID_ITEM_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown item_type: {item_type}")
    lib.detach_tag(conn, item_type=item_type, item_id=item_id, tag_id=tag_id)  # type: ignore[arg-type]
    return {"ok": "true"}
