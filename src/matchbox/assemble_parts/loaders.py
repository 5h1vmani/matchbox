"""DB loaders for the assemble pipeline: job, profile, verified/unverified
bullets, and cached JD requirements. Extracted from assemble.py."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from matchbox.matching.select import Component, Requirement


def _load_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise LookupError(f"job {job_id} not found in DB")
    return dict(row)


def _load_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profile LIMIT 1").fetchone()
    return dict(row) if row is not None else {}


def _load_components(
    conn: sqlite3.Connection,
) -> tuple[list[Component], dict[int, dict[str, Any]]]:
    """Verified bullets only. Returns (Components, raw_bullet_by_id)."""
    rows = conn.execute(
        """
        SELECT b.id, b.experience_id, b.text, b.has_metric,
               e.company, e.role, e.start_date, e.end_date, e.location, e.sort_order
          FROM bullet b
          JOIN experience e ON e.id = b.experience_id
         WHERE b.facts_verified = 1
         ORDER BY e.sort_order, e.id, b.id
        """
    ).fetchall()
    comps = [
        Component(
            id=r["id"],
            text=r["text"],
            experience_id=r["experience_id"],
            has_metric=bool(r["has_metric"]),
            end_date=r["end_date"],
        )
        for r in rows
    ]
    raw = {r["id"]: dict(r) for r in rows}
    return comps, raw


def _load_verified_projects(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Verified projects only, keyed by id. Selection may place these in the
    Projects section; unverified projects are never renderable (the same hard
    rule as bullets)."""
    rows = conn.execute(
        "SELECT id, name, text, url FROM project WHERE facts_verified = 1 ORDER BY id"
    ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def _load_unverified_bullets(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """(id, text) for every NOT-yet-verified bullet.

    Selection never touches these (the hard rule: no unverified content on the
    CV). They are consulted only for the coverage diagnostic, so a must-have the
    user genuinely has experience for -- but has not verified -- reads `partial`
    rather than a false `uncovered`."""
    rows = conn.execute(
        "SELECT id, text FROM bullet WHERE facts_verified = 0 ORDER BY id"
    ).fetchall()
    return [(r["id"], r["text"]) for r in rows]


def _load_requirements(conn: sqlite3.Connection, job_id: int) -> list[Requirement]:
    row = conn.execute("SELECT requirements_json FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None or not row["requirements_json"]:
        return []
    payload = json.loads(row["requirements_json"])
    return [
        Requirement(
            text=r["text"],
            type=r["type"],
            keywords=r.get("keywords", []),
            variants=r.get("variants", []),
        )
        for r in payload.get("requirements", [])
    ]
