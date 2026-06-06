"""Review screen — confirm or edit components extracted by the brain.

This is the v0.3 guardrail (section 9 item 5): the user reviews every
extracted bullet, edits text and tags, deletes noise, and confirms.
Confirming flips `facts_verified` from false to true.
"""

from __future__ import annotations

import sqlite3
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from matchbox.core import library as lib
from matchbox.core.models import Bullet, Project, TaggedItem
from matchbox.web.deps import ConnDep
from matchbox.web.templates_env import templates

router = APIRouter()


def _block(conn: sqlite3.Connection, experience_id: int) -> dict[str, Any]:
    exp = lib.get_experience(conn, experience_id)
    bullets = lib.bullets_with_tags(conn, experience_id=experience_id)
    verified = sum(1 for b in bullets if cast(Bullet, b.item).facts_verified)
    return {
        "experience": exp,
        "bullets": bullets,
        "verified_count": verified,
        "total_count": len(bullets),
    }


def _bullet_tagged(conn: sqlite3.Connection, bullet_id: int) -> TaggedItem:
    return TaggedItem(
        kind="bullet",
        item=lib.get_bullet(conn, bullet_id),
        tags=lib.tags_for(conn, item_type="bullet", item_id=bullet_id),
    )


def _project_tagged(conn: sqlite3.Connection, project_id: int) -> TaggedItem:
    return TaggedItem(
        kind="project",
        item=lib.get_project(conn, project_id),
        tags=lib.tags_for(conn, item_type="project", item_id=project_id),
    )


@router.get("/review", response_class=HTMLResponse)
def review_index(request: Request, conn: ConnDep) -> HTMLResponse:
    experiences = lib.list_experiences(conn)
    experience_blocks = [_block(conn, e.id) for e in experiences]
    projects = lib.projects_with_tags(conn)

    unverified_bullets = 0
    for blk in experience_blocks:
        for b in blk["bullets"]:
            if not cast(Bullet, b.item).facts_verified:
                unverified_bullets += 1
    unverified_projects = sum(1 for p in projects if not cast(Project, p.item).facts_verified)

    return templates.TemplateResponse(
        request,
        "onboarding/review.html.j2",
        {
            "experience_blocks": experience_blocks,
            "projects": projects,
            "unverified_bullets": unverified_bullets,
            "unverified_projects": unverified_projects,
        },
    )


@router.post("/review/bullets/{bullet_id}/verify", response_class=HTMLResponse)
def verify_bullet(request: Request, bullet_id: int, conn: ConnDep) -> HTMLResponse:
    lib.update_bullet(conn, bullet_id, facts_verified=True)
    return templates.TemplateResponse(
        request,
        "onboarding/_review_bullet.html.j2",
        {"tagged": _bullet_tagged(conn, bullet_id)},
    )


@router.post("/review/bullets/{bullet_id}/unverify", response_class=HTMLResponse)
def unverify_bullet(request: Request, bullet_id: int, conn: ConnDep) -> HTMLResponse:
    lib.update_bullet(conn, bullet_id, facts_verified=False)
    return templates.TemplateResponse(
        request,
        "onboarding/_review_bullet.html.j2",
        {"tagged": _bullet_tagged(conn, bullet_id)},
    )


@router.post("/review/experiences/{exp_id}/verify-all", response_class=HTMLResponse)
def verify_all_in_experience(request: Request, exp_id: int, conn: ConnDep) -> HTMLResponse:
    """Mark every bullet in this experience as verified."""
    conn.execute("UPDATE bullet SET facts_verified = 1 WHERE experience_id = ?", (exp_id,))
    return templates.TemplateResponse(
        request,
        "onboarding/_review_experience_block.html.j2",
        {"block": _block(conn, exp_id)},
    )


@router.post("/review/verify-all", response_class=HTMLResponse)
def verify_all(request: Request, conn: ConnDep) -> HTMLResponse:
    """Mark every unverified bullet across the whole library + every
    unverified project as verified. Returns the refreshed review page
    so the user can see the change in context.
    """
    conn.execute("UPDATE bullet SET facts_verified = 1 WHERE facts_verified = 0")
    conn.execute("UPDATE project SET facts_verified = 1 WHERE facts_verified = 0")
    # Re-render the full review screen.
    return review_index(request=request, conn=conn)


@router.post("/review/projects/{project_id}/verify", response_class=HTMLResponse)
def verify_project(request: Request, project_id: int, conn: ConnDep) -> HTMLResponse:
    conn.execute("UPDATE project SET facts_verified = 1 WHERE id = ?", (project_id,))
    return templates.TemplateResponse(
        request,
        "onboarding/_review_project.html.j2",
        {"tagged": _project_tagged(conn, project_id)},
    )


@router.delete("/review/bullets/{bullet_id}", response_class=Response)
def delete_bullet(bullet_id: int, conn: ConnDep) -> Response:
    lib.delete_bullet(conn, bullet_id)
    return Response(status_code=200)


@router.delete("/review/projects/{project_id}", response_class=Response)
def delete_project(project_id: int, conn: ConnDep) -> Response:
    lib.delete_project(conn, project_id)
    return Response(status_code=200)
