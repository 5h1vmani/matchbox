"""JSON API for the reusable answer library (prefix /api/answers).

Powers the Apply packet's Questions tab and the Library Answers tab. Each answer
carries its verified status and usage count; the matcher/UI surfaces the source,
and optional questions stay blank rather than being fabricated.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.answers import repo
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/answers")


class CreateBody(BaseModel):
    question: str
    answer: str
    category: str | None = None
    verified: bool = False


class UpdateBody(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    verified: bool | None = None


def _require(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail="no such answer")
    return row


@router.get("")
def list_answers(conn: ConnDep, verified: int | None = None) -> list[dict[str, Any]]:
    flag = None if verified is None else bool(verified)
    return repo.list_all(conn, verified=flag)


@router.post("")
def create_answer(body: CreateBody, conn: ConnDep) -> dict[str, Any]:
    if not body.question.strip() or not body.answer.strip():
        raise HTTPException(status_code=400, detail="question and answer are required")
    aid = repo.create(
        conn,
        question=body.question.strip(),
        answer=body.answer.strip(),
        category=(body.category or None),
        facts_verified=body.verified,
    )
    return _require(repo.get(conn, aid))


@router.patch("/{answer_id}")
def update_answer(answer_id: int, body: UpdateBody, conn: ConnDep) -> dict[str, Any]:
    return _require(
        repo.update(
            conn,
            answer_id,
            question=body.question,
            answer=body.answer,
            category=body.category,
            facts_verified=body.verified,
        )
    )


@router.post("/{answer_id}/use")
def use_answer(answer_id: int, conn: ConnDep) -> dict[str, Any]:
    """Increment usage when the answer is selected for an application."""
    return _require(repo.mark_used(conn, answer_id))


@router.delete("/{answer_id}")
def delete_answer(answer_id: int, conn: ConnDep) -> dict[str, str]:
    repo.delete(conn, answer_id)
    return {"ok": "true"}
