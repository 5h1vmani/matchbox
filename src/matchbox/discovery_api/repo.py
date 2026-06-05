"""Discovery persistence + serialization (the DAL).

Serializes each scored `job` (left-joined to its `ats_source`) into the exact
`Role` view-model the SPA consumes, loads the role set / watchlist, and performs
the decision writes. Keeps SQL in one place. Only scored jobs (those with a
`score_breakdown_json`) enter discovery — unscored rows need an upstream
scoring run and are simply not selected here.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from matchbox.core.db import PROJECT_ROOT, transaction
from matchbox.discovery_api import rules
from matchbox.matching.coverage import summarize_coverage
from matchbox.tracker.rules import mono_for

_RUNS_DIR = PROJECT_ROOT / "runs"

# Scored jobs only, with the ATS source for the display label. Salary columns
# (added in 007_sota.sql) are serialized when the ad reported them; coverage is
# read from the tailoring artifact when a run exists for the job (see
# `_coverage_for_job`).
_ROLE_SELECT = """
  SELECT j.id, j.company, j.title, j.location, j.url, j.apply_url, j.jd_text,
         j.posted_at, j.score, j.score_breakdown_json,
         j.remote, j.discovery_decision, j.skipped_on, j.freshness, j.closes_at,
         j.sponsorship, j.citizenship_required, j.clearance_required, j.remote_scope,
         j.salary_min, j.salary_max, j.salary_currency, j.salary_period,
         s.ats_type AS ats_type
    FROM job j
    LEFT JOIN ats_source s ON s.id = j.source
   WHERE j.score_breakdown_json IS NOT NULL
"""


def serialize(
    row: sqlite3.Row,
    today: date | None = None,
    *,
    jd_preview: bool = False,
    work_auth: dict[str, Any] | None = None,
    coverage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """One scored `job` row -> the design's `Role` shape.

    `jd_preview` trims the JD to a short pulled line for the list surface (the JD
    drawer fetches the full text via load_one). `work_auth` (the user's target
    work-authorization) feeds the deterministic eligibility pre-filter.
    `coverage` (`{covered, total}`) is supplied by the caller when a tailoring
    run has produced a coverage report for this job; None means no run yet."""
    today = today or date.today()
    breakdown = rules.load_breakdown(row["score_breakdown_json"])

    level = rules.fit_level(row["score"], (breakdown or {}).get("band"))
    fit = {"level": level, "reason": rules.fit_reason(breakdown)}
    elig = rules.eligibility_status(
        breakdown,
        sponsorship=row["sponsorship"],
        citizenship_required=row["citizenship_required"],
        clearance_required=row["clearance_required"],
        work_auth=work_auth,
    )
    fresh, closing_in = rules.freshness(row["freshness"], row["closes_at"], today)
    jd = rules.jd_paragraphs(row["jd_text"])
    if jd_preview:
        jd = [rules.jd_teaser(jd[0])] if jd else []

    return {
        "id": str(row["id"]),
        "company": row["company"],
        "title": row["title"],
        "location": row["location"] or "",
        "remote": bool(row["remote"]),
        "salary": rules.salary_display(
            row["salary_min"], row["salary_max"], row["salary_currency"], row["salary_period"]
        ),
        "source": rules.source_label(row["ats_type"]),
        "postedDaysAgo": rules.days_since(row["posted_at"], today),
        "link": row["apply_url"] or row["url"],
        "fit": fit,
        "eligibility": elig,
        # Coverage is real only once a tailoring run has matched this job's
        # requirements against the verified library; null until then.
        "coverage": coverage,
        "freshness": fresh,
        "closingInDays": closing_in,
        "mono": mono_for(row["company"]),
        "jd": jd,
        "decision": row["discovery_decision"],
    }


def _coverage_for_job(conn: sqlite3.Connection, job_id: int) -> dict[str, int] | None:
    """`{covered, total}` from the most recent tailoring run's coverage.json for
    this job, or None when no run has produced one yet. Honest: the bar appears
    only once the requirements were actually matched against the verified
    library -- never inferred."""
    row = conn.execute(
        "SELECT run_id FROM run_job WHERE job_id = ? ORDER BY run_id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    path = _RUNS_DIR / row["run_id"] / "output" / str(job_id) / "coverage.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return summarize_coverage(data)


def _skipped_today(skipped_on: str | None, today: date) -> bool:
    return bool(skipped_on) and (skipped_on or "")[:10] == today.isoformat()


def _work_auth(conn: sqlite3.Connection) -> dict[str, Any]:
    """The user's work-authorization block from `target` (for the eligibility
    pre-filter). Empty dict when unset -- then nothing is ruled out."""
    row = conn.execute("SELECT work_auth_json FROM target LIMIT 1").fetchone()
    if not row or not row["work_auth_json"]:
        return {}
    try:
        val = json.loads(row["work_auth_json"])
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def load_roles(conn: sqlite3.Connection, today: date | None = None) -> list[dict[str, Any]]:
    """All scored roles, minus those skipped today (they return tomorrow),
    serialized slim (JD trimmed to its first paragraph for the card's pulled
    line; the drawer fetches the full text via load_one).

    The SPA owns queue/browse membership, ordering, and the cap client-side —
    byte-identical to the design prototype — so this stays a thin serializer
    (the single source of that logic lives where the design put it)."""
    today = today or date.today()
    wa = _work_auth(conn)
    rows = conn.execute(_ROLE_SELECT).fetchall()
    return [
        serialize(
            r, today, jd_preview=True, work_auth=wa, coverage=_coverage_for_job(conn, r["id"])
        )
        for r in rows
        if not _skipped_today(r["skipped_on"], today)
    ]


def load_watchlist(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Watched companies + a live count of their open, eligible, scored roles."""
    rows = conn.execute(
        "SELECT company, note, status FROM watchlist ORDER BY id DESC"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for w in rows:
        open_roles = _open_eligible_count(conn, w["company"])
        out.append(
            {
                "company": w["company"],
                "note": w["note"] or "",
                "status": w["status"] or "watching",
                "openRoles": open_roles,
                "mono": mono_for(w["company"]),
            }
        )
    return out


def _open_eligible_count(conn: sqlite3.Connection, company: str) -> int:
    """Open, eligible (not judged ineligible), scored, undecided roles at a company."""
    wa = _work_auth(conn)
    rows = conn.execute(
        _ROLE_SELECT + " AND j.company = ? AND j.discovery_decision IS NULL",
        (company,),
    ).fetchall()
    count = 0
    for r in rows:
        role = serialize(r, work_auth=wa)
        if role["eligibility"]["status"] != "ineligible" and role["freshness"] != "closed":
            count += 1
    return count


# ── reads for one role ─────────────────────────────────────────────────────────


def raw(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        _ROLE_SELECT + " AND j.id = ?", (job_id,)
    ).fetchone()
    return row


def load_one(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = raw(conn, job_id)
    if row is None:
        return None
    return serialize(
        row, work_auth=_work_auth(conn), coverage=_coverage_for_job(conn, job_id)
    )


def job_facts(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    """Company/title/url for the decision effects (works for any job, scored or not)."""
    row: sqlite3.Row | None = conn.execute(
        "SELECT id, company, title, url, apply_url FROM job WHERE id = ?", (job_id,)
    ).fetchone()
    return row


# ── writes ─────────────────────────────────────────────────────────────────────


def set_decision(conn: sqlite3.Connection, job_id: int, decision: str | None) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE job SET discovery_decision = ? WHERE id = ?", (decision, job_id)
        )


def set_skipped(conn: sqlite3.Connection, job_id: int, when: str) -> None:
    with transaction(conn):
        conn.execute("UPDATE job SET skipped_on = ? WHERE id = ?", (when, job_id))


def existing_application(conn: sqlite3.Connection, job_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM application WHERE job_id = ? ORDER BY id LIMIT 1", (job_id,)
    ).fetchone()
    return int(row["id"]) if row else None


def create_application(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    stage: str = "saved",
    run_id: str | None = None,
) -> int:
    """Create a tracker `application` for a job (idempotent per job).

    Inserts with the legacy `status='draft'` (the table's CHECK), and the
    tracker's `stage` (what the tracker SPA reads). Seeds `updated_at` and a
    'saved' history event so the timeline is not empty.
    """
    existing = existing_application(conn, job_id)
    if existing is not None:
        if run_id is not None:
            with transaction(conn):
                conn.execute(
                    "UPDATE application SET run_id = COALESCE(run_id, ?) WHERE id = ?",
                    (run_id, existing),
                )
        return existing

    # Snapshot the predicted fit at apply-time so Learn can calibrate later.
    job = conn.execute(
        "SELECT score, score_breakdown_json FROM job WHERE id = ?", (job_id,)
    ).fetchone()
    predicted_score = job["score"] if job else None
    predicted_band = (
        (rules.load_breakdown(job["score_breakdown_json"]) or {}).get("band")
        if job and job["score_breakdown_json"]
        else None
    )
    with transaction(conn):
        cur = conn.execute(
            """
            INSERT INTO application (job_id, run_id, status, stage, has_draft,
                                     updated_at, predicted_band, predicted_score)
            VALUES (?, ?, 'draft', ?, 0,
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?)
            """,
            (job_id, run_id, stage, predicted_band, predicted_score),
        )
        app_id = int(cur.lastrowid or 0)
        conn.execute(
            "INSERT INTO app_event (application_id, kind, text) VALUES (?, 'saved', 'Saved from discovery')",
            (app_id,),
        )
    return app_id


def upsert_watchlist(conn: sqlite3.Connection, company: str, note: str | None = None) -> None:
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO watchlist (company, note, status)
            VALUES (?, ?, 'watching')
            ON CONFLICT(company) DO UPDATE SET note = COALESCE(excluded.note, watchlist.note)
            """,
            (company, note or "Watching for a role you're eligible for."),
        )


def is_dismissed_duplicate(
    conn: sqlite3.Connection, *, url: str | None, company: str, title: str
) -> bool:
    """Whether an incoming job matches a previously dismissed one (spec §6 dedupe:
    match on `url`, else `company`+`title`)."""
    if url:
        row = conn.execute(
            "SELECT 1 FROM job WHERE discovery_decision = 'dismissed' AND url = ? LIMIT 1",
            (url,),
        ).fetchone()
        if row:
            return True
    row = conn.execute(
        "SELECT 1 FROM job WHERE discovery_decision = 'dismissed' "
        "AND company = ? AND title = ? LIMIT 1",
        (company, title),
    ).fetchone()
    return row is not None
