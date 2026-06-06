"""Jobs JSON API (prefix /api/jobs) — add a role by hand + score new roles.

The React replacement for the inbox "add a job by hand" + "score new jobs"
affordances. A hand-added role lands with `source = NULL` and `status = 'new'`,
enriched by the deterministic Tier-2 regexes, so the existing score / triage /
tailor flow picks it up like any scanned role. Only scored roles enter Discover.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from matchbox.discovery import enrich
from matchbox.matching.embed import Embedder, FastEmbedEmbedder
from matchbox.scoring.rubric import score_all_new
from matchbox.web.deps import ConnDep

router = APIRouter(prefix="/api/jobs")


class JobBody(BaseModel):
    company: str
    title: str
    url: str
    jd_text: str
    apply_url: str | None = None
    location: str | None = None


def _scoring_embedder() -> Embedder | None:
    """Real embedder in production; None (lexical-only) when
    MATCHBOX_DISABLE_SEMANTIC is set (tests stay offline)."""
    if os.environ.get("MATCHBOX_DISABLE_SEMANTIC"):
        return None
    try:
        return FastEmbedEmbedder()
    except Exception:
        return None


@router.post("")
def add_job(body: JobBody, conn: ConnDep) -> dict[str, Any]:
    """Add a role by hand from a URL + pasted JD (LinkedIn, careers pages,
    referrals -- anything not on a polled ATS)."""
    company, title, url, jd = (
        body.company.strip(),
        body.title.strip(),
        body.url.strip(),
        body.jd_text.strip(),
    )
    if not (company and title and url and jd):
        raise HTTPException(status_code=400, detail="company, title, url, and jd_text are required")
    rec = enrich.enrich_record(title, jd)
    try:
        cur = conn.execute(
            """
            INSERT INTO job
                (source, company, title, location, url, apply_url, jd_text, status,
                 dedup_key, seniority, min_years_exp, role_family, sponsorship,
                 citizenship_required, clearance_required, remote_scope)
            VALUES (NULL, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                title,
                (body.location or "").strip() or None,
                url,
                (body.apply_url or "").strip() or None,
                jd,
                enrich.dedup_key(url, company, title, (body.location or "").strip() or None),
                rec["seniority"],
                rec["min_years_exp"],
                rec["role_family"],
                rec["sponsorship"],
                rec["citizenship_required"],
                rec["clearance_required"],
                rec["remote_scope"],
            ),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"a job with url {url!r} already exists") from e
    return {"id": int(cur.lastrowid or 0), "status": "new"}


@router.post("/score-new")
def score_new(conn: ConnDep) -> dict[str, int]:
    """Score every `new` role so it enters Discover. Returns the count scored."""
    n = score_all_new(conn, embedder=_scoring_embedder())
    return {"scored": n}
