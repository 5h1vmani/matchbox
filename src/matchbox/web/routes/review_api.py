"""Review JSON API (prefix /api/review) for the React Review screen.

The v0.3 guardrail: the user reviews every extracted component and confirms.
Confirming flips `facts_verified` false -> true. Reuses the library DAL; verified
is binary (no trust-ring %).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.answers import repo as answers_repo
from matchbox.core import library as lib
from matchbox.core.models import Bullet, Project
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/review")


class BulletEdit(BaseModel):
    text: str | None = None
    has_metric: bool | None = None


def _bullet_vm(b: Bullet) -> dict[str, Any]:
    return {
        "id": b.id,
        "experienceId": b.experience_id,
        "text": b.text,
        "hasMetric": b.has_metric,
        "verified": b.facts_verified,
        "sourceFile": b.source_file,
    }


@router.get("")
def review_state(conn: ConnDep) -> dict[str, Any]:
    """Every component grouped for review, with unverified counts."""
    experiences = []
    unverified_bullets = 0
    for e in lib.list_experiences(conn):
        bullets = [cast(Bullet, t.item) for t in lib.bullets_with_tags(conn, experience_id=e.id)]
        unverified_bullets += sum(1 for b in bullets if not b.facts_verified)
        experiences.append(
            {
                "id": e.id,
                "company": e.company,
                "role": e.role,
                "startDate": e.start_date,
                "endDate": e.end_date,
                "bullets": [_bullet_vm(b) for b in bullets],
            }
        )
    projects = [cast(Project, t.item) for t in lib.projects_with_tags(conn)]
    answers = answers_repo.list_all(conn)
    return {
        "experiences": experiences,
        "projects": [
            {"id": p.id, "name": p.name, "text": p.text, "url": p.url, "verified": p.facts_verified}
            for p in projects
        ],
        "answers": answers,
        "unverifiedBullets": unverified_bullets,
        "unverifiedProjects": sum(1 for p in projects if not p.facts_verified),
        "unverifiedAnswers": sum(1 for a in answers if not a["verified"]),
    }


@router.get("/counts")
def review_counts(conn: ConnDep) -> dict[str, int]:
    """Cheap progress poll for the Onboarding screen: how many bullets the
    ingest has landed and how many the user has verified. The screen polls this
    while the user runs `ingest my files` in Claude Code, so progress is
    visible in-app instead of only in the terminal."""
    bullets = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(facts_verified), 0) AS v FROM bullet"
    ).fetchone()
    experiences = conn.execute("SELECT COUNT(*) AS n FROM experience").fetchone()
    return {
        "bullets": int(bullets["n"]),
        "verified": int(bullets["v"]),
        "experiences": int(experiences["n"]),
    }


@router.post("/bullets/{bullet_id}/verify")
def verify_bullet(bullet_id: int, conn: ConnDep) -> dict[str, Any]:
    return _bullet_vm(lib.update_bullet(conn, bullet_id, facts_verified=True))


@router.post("/bullets/{bullet_id}/unverify")
def unverify_bullet(bullet_id: int, conn: ConnDep) -> dict[str, Any]:
    return _bullet_vm(lib.update_bullet(conn, bullet_id, facts_verified=False))


@router.patch("/bullets/{bullet_id}")
def edit_bullet(bullet_id: int, body: BulletEdit, conn: ConnDep) -> dict[str, Any]:
    return _bullet_vm(
        lib.update_bullet(conn, bullet_id, text=body.text, has_metric=body.has_metric)
    )


@router.delete("/bullets/{bullet_id}")
def delete_bullet(bullet_id: int, conn: ConnDep) -> dict[str, str]:
    lib.delete_bullet(conn, bullet_id)
    return {"ok": "true"}


@router.post("/experiences/{exp_id}/verify-all")
def verify_experience(exp_id: int, conn: ConnDep) -> dict[str, Any]:
    conn.execute("UPDATE bullet SET facts_verified = 1 WHERE experience_id = ?", (exp_id,))
    bullets = lib.list_bullets(conn, experience_id=exp_id)
    return {"experienceId": exp_id, "bullets": [_bullet_vm(b) for b in bullets]}


@router.post("/verify-all")
def verify_all(conn: ConnDep) -> dict[str, Any]:
    """Mark every unverified bullet, project, and answer as verified."""
    conn.execute("UPDATE bullet SET facts_verified = 1 WHERE facts_verified = 0")
    conn.execute("UPDATE project SET facts_verified = 1 WHERE facts_verified = 0")
    conn.execute("UPDATE answer SET facts_verified = 1 WHERE facts_verified = 0")
    return review_state(conn)


@router.post("/projects/{project_id}/verify")
def verify_project(project_id: int, conn: ConnDep) -> dict[str, Any]:
    conn.execute("UPDATE project SET facts_verified = 1 WHERE id = ?", (project_id,))
    p = lib.get_project(conn, project_id)
    return {"id": p.id, "name": p.name, "text": p.text, "url": p.url, "verified": p.facts_verified}


@router.post("/answers/{answer_id}/verify")
def verify_answer(answer_id: int, conn: ConnDep) -> dict[str, Any]:
    row = answers_repo.update(conn, answer_id, facts_verified=True)
    if row is None:
        raise HTTPException(status_code=404, detail="no such answer")
    return row
