"""
matchbox/shared/db.py — SQLite access layer for Matchbox pipeline state.

This file is the ONLY place that contains SQL. All agents call the functions
defined here. Enforcement: no other file should import sqlite3 directly.

Schema defined inline; initialised on first use.

Engineering principles:
- SSOT: SQLite is the single source of truth for pipeline state.
- DRY: one function per operation; no SQL duplication.
- Single responsibility: this file does persistence and nothing else.
- Least privilege: functions return narrow column sets; callers ask only for what they need.
- Fail closed: any DB error raises; no silent failures.
- Auditability: every scan_run row logs what the scan did and cost.

Usage:
    from matchbox.shared import db

    db.init_db(profile="shiva")                       # idempotent
    run_id = db.create_scan_run(profile="shiva", mode="dream", country="india")
    job_id = db.insert_job(run_id=run_id, profile_name="shiva", ...)
    jobs = db.list_jobs(profile="shiva", filters={"min_score": 4.0, "state": "evaluated"})
    db.update_job_state(job_id=job_id, new_state="applied", note="submitted 2026-04-21")
    hot = db.get_hot_companies(profile="shiva", days=14)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


# ============================================================
# Paths and connection
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def db_path(profile: str) -> Path:
    """Return the SQLite file path for a given profile."""
    return REPO_ROOT / "matchbox" / "people" / profile / "db" / "matchbox.db"


@contextmanager
def _connect(profile: str) -> Iterator[sqlite3.Connection]:
    """Context manager that yields a connection with Row factory and foreign keys enabled."""
    path = db_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better concurrency for parallel Haiku workers
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# Schema (created on first call to init_db)
# ============================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name       TEXT NOT NULL,
    mode               TEXT,
    country            TEXT,
    started_at         TEXT NOT NULL,
    completed_at       TEXT,
    raw_candidates     INTEGER DEFAULT 0,
    filtered_survivors INTEGER DEFAULT 0,
    scored_count       INTEGER DEFAULT 0,
    apply_count        INTEGER DEFAULT 0,
    review_count       INTEGER DEFAULT 0,
    skip_count         INTEGER DEFAULT 0,
    cost_usd           REAL DEFAULT 0.0,
    status             TEXT NOT NULL DEFAULT 'running',
    notes              TEXT,
    is_trial           INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name       TEXT NOT NULL,
    scan_run_id        INTEGER REFERENCES scan_runs(id),

    -- Discovery metadata
    company            TEXT NOT NULL,
    role               TEXT NOT NULL,
    location           TEXT,
    country            TEXT,
    url                TEXT NOT NULL,
    mode               TEXT,
    ats_source         TEXT,
    posting_date       TEXT,
    discovered_date    TEXT NOT NULL,

    -- JD data
    jd_summary         TEXT,
    comp_stated        TEXT,
    visa_sponsorship   TEXT,
    legitimacy         TEXT,

    -- Scoring (5 dimensions + total)
    cv_match_score     REAL,
    north_star_score   REAL,
    comp_score         REAL,
    cultural_score     REAL,
    red_flags_score    REAL,
    total_score        REAL,
    recommendation     TEXT,
    report_path        TEXT,

    -- Pipeline state
    state              TEXT NOT NULL DEFAULT 'evaluated',
    cv_generated       INTEGER DEFAULT 0,
    cover_generated    INTEGER DEFAULT 0,
    cv_path            TEXT,
    cover_path         TEXT,
    applied_date       TEXT,
    response_date      TEXT,
    interview_notes    TEXT,
    rejection_reason   TEXT,
    user_notes         TEXT,

    -- Link health (populated by check_url / bulk_check_urls)
    url_last_checked   TEXT,
    url_http_status    INTEGER,

    -- 2026-04-21: 6-dim scoring (north_star split).
    -- Legacy north_star_score column above kept NULL-able for old rows.
    company_mission_fit_score REAL,
    role_mission_fit_score    REAL,

    -- 2026-04-21: UX + policy
    is_starred          INTEGER DEFAULT 0,
    role_family         TEXT,
    exclusion_triggered TEXT,
    dream_tier          TEXT,

    -- Audit
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE (profile_name, url)
);

CREATE INDEX IF NOT EXISTS idx_jobs_profile_state ON jobs(profile_name, state);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_country ON jobs(country);
CREATE INDEX IF NOT EXISTS idx_jobs_mode ON jobs(mode);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
FOR EACH ROW
BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;
"""


# Columns that must exist on the `jobs` table. Used by _migrate to add missing
# columns to DBs created before a column was introduced. Each entry is
# (column_name, column_definition). Migrations are idempotent.
_JOBS_REQUIRED_COLUMNS: list[tuple[str, str]] = [
    # Link health
    ("url_last_checked",           "TEXT"),
    ("url_http_status",            "INTEGER"),
    # 2026-04-21: 6-dim scoring (north_star split). Legacy north_star_score
    # column is preserved above for old rows; new scans populate both new
    # columns and leave north_star_score NULL.
    ("company_mission_fit_score",  "REAL"),
    ("role_mission_fit_score",     "REAL"),
    # 2026-04-21: UX + policy
    ("is_starred",                 "INTEGER DEFAULT 0"),  # user-pinned
    ("role_family",                "TEXT"),               # matched against role_family_preference
    ("exclusion_triggered",        "TEXT"),               # e.g. 'defense|us' if sector exclusion fired
    ("dream_tier",                 "TEXT"),               # tier_1_dream | tier_2_target | tier_3_watchlist | tier_4_exploratory | null
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any missing columns on existing DBs. Idempotent."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, defn in _JOBS_REQUIRED_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {defn}")


def init_db(profile: str) -> None:
    """Idempotently create schema and run migrations. Safe to call at every entry point."""
    with _connect(profile) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)


# ============================================================
# Canonical state set (must match matchbox/shared/states.yml)
# ============================================================

VALID_STATES = {
    "evaluated",          # scored, awaiting user decision
    "queued_for_tailor",  # UI queued it for tailoring
    "tailored",           # CV (+cover) produced, awaiting user review
    "applied",            # user submitted
    "responded",          # company replied
    "interview",          # interview scheduled
    "offer",              # offer received
    "rejected",           # rejected by company
    "discarded",          # user withdrew / closed
    "skip",               # auto-skipped (score < threshold, ghost, etc)
    "cooling",            # frozen pending sibling apps at same company (user-chosen pause)
}


def _assert_state(state: str) -> None:
    if state not in VALID_STATES:
        raise ValueError(f"Invalid state '{state}'. Valid: {sorted(VALID_STATES)}")


# ============================================================
# Scan runs
# ============================================================

def create_scan_run(
    profile: str,
    mode: str | None = None,
    country: str | None = None,
    is_trial: bool = False,
) -> int:
    """Start a new scan run. Returns scan_run_id."""
    init_db(profile)
    with _connect(profile) as conn:
        cursor = conn.execute(
            """
            INSERT INTO scan_runs (profile_name, mode, country, started_at, status, is_trial)
            VALUES (?, ?, ?, datetime('now'), 'running', ?)
            """,
            (profile, mode, country, 1 if is_trial else 0),
        )
        return cursor.lastrowid or 0


def complete_scan_run(
    profile: str,
    run_id: int,
    *,
    raw_candidates: int = 0,
    filtered_survivors: int = 0,
    scored_count: int = 0,
    apply_count: int = 0,
    review_count: int = 0,
    skip_count: int = 0,
    cost_usd: float = 0.0,
    status: str = "success",
    notes: str | None = None,
) -> None:
    """Finalise a scan run with its counts and status."""
    with _connect(profile) as conn:
        conn.execute(
            """
            UPDATE scan_runs
               SET completed_at       = datetime('now'),
                   raw_candidates     = ?,
                   filtered_survivors = ?,
                   scored_count       = ?,
                   apply_count        = ?,
                   review_count       = ?,
                   skip_count         = ?,
                   cost_usd           = ?,
                   status             = ?,
                   notes              = ?
             WHERE id = ?
            """,
            (raw_candidates, filtered_survivors, scored_count, apply_count,
             review_count, skip_count, cost_usd, status, notes, run_id),
        )


def get_scan_history(profile: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the last N scan runs as list of dicts."""
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute(
            "SELECT * FROM scan_runs WHERE profile_name = ? ORDER BY started_at DESC LIMIT ?",
            (profile, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# Jobs: insert and update
# ============================================================

def insert_job(
    profile_name: str,
    run_id: int | None,
    *,
    company: str,
    role: str,
    url: str,
    discovered_date: str | None = None,
    location: str | None = None,
    country: str | None = None,
    mode: str | None = None,
    ats_source: str | None = None,
    posting_date: str | None = None,
    jd_summary: str | None = None,
    comp_stated: str | None = None,
    visa_sponsorship: str | None = None,
    legitimacy: str | None = None,
    cv_match_score: float | None = None,
    north_star_score: float | None = None,
    comp_score: float | None = None,
    cultural_score: float | None = None,
    red_flags_score: float | None = None,
    total_score: float | None = None,
    recommendation: str | None = None,
    report_path: str | None = None,
    state: str = "evaluated",
) -> int:
    """
    Insert a single job. Returns job_id. Raises if (profile_name, url) already exists.
    Use bulk_insert_jobs for many rows.
    """
    _assert_state(state)
    init_db(profile_name)
    discovered = discovered_date or datetime.now(timezone.utc).date().isoformat()

    with _connect(profile_name) as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (
                profile_name, scan_run_id, company, role, url, discovered_date,
                location, country, mode, ats_source, posting_date,
                jd_summary, comp_stated, visa_sponsorship, legitimacy,
                cv_match_score, north_star_score,
                company_mission_fit_score, role_mission_fit_score,
                comp_score, cultural_score, red_flags_score, total_score,
                recommendation, report_path, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (profile_name, run_id, company, role, url, discovered,
             location, country, mode, ats_source, posting_date,
             jd_summary, comp_stated, visa_sponsorship, legitimacy,
             cv_match_score, north_star_score,
             None, None,  # company_mission_fit_score, role_mission_fit_score — callers of insert_job should use update_job to set
             comp_score, cultural_score,
             red_flags_score, total_score, recommendation, report_path, state),
        )
        return cursor.lastrowid or 0


def bulk_insert_jobs(
    profile_name: str,
    run_id: int | None,
    jobs: Iterable[dict[str, Any]],
    *,
    skip_duplicates: bool = True,
) -> tuple[int, int]:
    """
    Insert many jobs. Returns (inserted_count, skipped_count).
    If skip_duplicates, UNIQUE violations on (profile_name, url) are silently ignored.
    """
    init_db(profile_name)
    inserted = 0
    skipped = 0

    with _connect(profile_name) as conn:
        for j in jobs:
            if "state" in j:
                _assert_state(j["state"])
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        profile_name, scan_run_id, company, role, url, discovered_date,
                        location, country, mode, ats_source, posting_date,
                        jd_summary, comp_stated, visa_sponsorship, legitimacy,
                        cv_match_score, north_star_score,
                        company_mission_fit_score, role_mission_fit_score,
                        comp_score, cultural_score, red_flags_score, total_score,
                        recommendation, report_path, state,
                        role_family, dream_tier, exclusion_triggered, is_starred
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (profile_name, run_id, j["company"], j["role"], j["url"],
                     j.get("discovered_date") or datetime.now(timezone.utc).date().isoformat(),
                     j.get("location"), j.get("country"), j.get("mode"),
                     j.get("ats_source"), j.get("posting_date"),
                     j.get("jd_summary"), j.get("comp_stated"),
                     j.get("visa_sponsorship"), j.get("legitimacy"),
                     j.get("cv_match_score"), j.get("north_star_score"),
                     j.get("company_mission_fit_score"), j.get("role_mission_fit_score"),
                     j.get("comp_score"), j.get("cultural_score"),
                     j.get("red_flags_score"), j.get("total_score"),
                     j.get("recommendation"), j.get("report_path"),
                     j.get("state", "evaluated"),
                     j.get("role_family"), j.get("dream_tier"),
                     j.get("exclusion_triggered"),
                     1 if j.get("is_starred") else 0),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                if skip_duplicates:
                    skipped += 1
                else:
                    raise
    return inserted, skipped


def update_job(profile: str, job_id: int, **fields: Any) -> None:
    """Update arbitrary fields on a job. Validates state if provided."""
    if not fields:
        return
    if "state" in fields:
        _assert_state(fields["state"])

    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]

    with _connect(profile) as conn:
        conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)


def update_job_state(
    profile: str,
    job_id: int,
    new_state: str,
    note: str | None = None,
) -> None:
    """Update state. If note provided, append to user_notes."""
    _assert_state(new_state)
    with _connect(profile) as conn:
        if note:
            conn.execute(
                """
                UPDATE jobs
                   SET state = ?,
                       user_notes = CASE
                           WHEN user_notes IS NULL THEN ?
                           ELSE user_notes || ' | ' || ?
                       END
                 WHERE id = ?
                """,
                (new_state, note, note, job_id),
            )
        else:
            conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (new_state, job_id))

        # If transitioning to applied, stamp the date
        if new_state == "applied":
            conn.execute(
                "UPDATE jobs SET applied_date = COALESCE(applied_date, date('now')) WHERE id = ?",
                (job_id,),
            )


# ============================================================
# Reads
# ============================================================

def get_job(profile: str, job_id: int) -> dict[str, Any] | None:
    """Return one job as a dict, or None if not found."""
    init_db(profile)
    with _connect(profile) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND profile_name = ?",
            (job_id, profile),
        ).fetchone()
        return dict(row) if row else None


def list_jobs(
    profile: str,
    *,
    state: str | list[str] | None = None,
    country: str | list[str] | None = None,
    mode: str | list[str] | None = None,
    recommendation: str | list[str] | None = None,
    dream_tier: str | list[str] | None = None,
    role_family: str | list[str] | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    min_cv_match: float | None = None,
    min_company_mission: float | None = None,
    min_role_mission: float | None = None,
    min_comp: float | None = None,
    min_cultural: float | None = None,
    min_red_flags: float | None = None,
    has_cv: bool | None = None,
    has_cover: bool | None = None,
    is_starred: bool | None = None,
    company_search: str | None = None,
    role_search: str | None = None,
    since_date: str | None = None,
    limit: int = 1000,
    order_by: str = "total_score DESC",
) -> list[dict[str, Any]]:
    """
    Query jobs with filters. All filters are AND-ed.
    state / country / mode / recommendation can be single value or list.
    Returns list of dicts.
    """
    init_db(profile)
    where = ["profile_name = ?"]
    params: list[Any] = [profile]

    def _in_clause(col: str, values: str | list[str]) -> None:
        if isinstance(values, str):
            where.append(f"{col} = ?")
            params.append(values)
        else:
            placeholders = ",".join("?" for _ in values)
            where.append(f"{col} IN ({placeholders})")
            params.extend(values)

    if state is not None:
        _in_clause("state", state)
    if country is not None:
        _in_clause("country", country)
    if mode is not None:
        _in_clause("mode", mode)
    if recommendation is not None:
        _in_clause("recommendation", recommendation)
    if dream_tier is not None:
        _in_clause("dream_tier", dream_tier)
    if role_family is not None:
        _in_clause("role_family", role_family)
    if min_score is not None:
        where.append("total_score >= ?")
        params.append(min_score)
    if max_score is not None:
        where.append("total_score <= ?")
        params.append(max_score)
    # Sub-score filters. Semantics:
    #  - threshold None OR 0 → no filter applied (matches "slider at zero").
    #  - For company_mission_fit_score and role_mission_fit_score, legacy rows
    #    (pre-2026-04-21 rubric split) have these columns NULL but still have
    #    north_star_score populated. Fall back: use COALESCE(new_col, north_star_score).
    #    New scans populate the split columns and leave north_star NULL.
    _subscore_filters: list[tuple[str, float | None]] = [
        ("cv_match_score",                                        min_cv_match),
        ("COALESCE(company_mission_fit_score, north_star_score)", min_company_mission),
        ("COALESCE(role_mission_fit_score,    north_star_score)", min_role_mission),
        ("comp_score",                                            min_comp),
        ("cultural_score",                                        min_cultural),
        ("red_flags_score",                                       min_red_flags),
    ]
    for col_expr, threshold in _subscore_filters:
        if threshold is not None and threshold > 0:
            where.append(f"{col_expr} >= ?")
            params.append(threshold)
    if has_cv is True:
        where.append("cv_generated = 1")
    elif has_cv is False:
        where.append("cv_generated = 0")
    if is_starred is True:
        where.append("is_starred = 1")
    elif is_starred is False:
        where.append("is_starred = 0")
    if has_cover is True:
        where.append("cover_generated = 1")
    elif has_cover is False:
        where.append("cover_generated = 0")
    if company_search:
        where.append("LOWER(company) LIKE ?")
        params.append(f"%{company_search.lower()}%")
    if role_search:
        where.append("LOWER(role) LIKE ?")
        params.append(f"%{role_search.lower()}%")
    if since_date:
        where.append("discovered_date >= ?")
        params.append(since_date)

    # Safe ordering: whitelist to prevent injection. Starred rows can
    # optionally float first via the "starred_first" variants.
    safe_orderings = {
        "total_score DESC":      "total_score DESC",
        "total_score ASC":       "total_score ASC",
        "discovered_date DESC":  "discovered_date DESC",
        "company ASC":           "company ASC",
        "state ASC":             "state ASC",
        "created_at DESC":       "created_at DESC",
        "starred_first":         "is_starred DESC, total_score DESC",
        "cv_match DESC":         "cv_match_score DESC",
        "role_mission DESC":     "role_mission_fit_score DESC",
    }
    order = safe_orderings.get(order_by, "total_score DESC")

    query = f"SELECT * FROM jobs WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?"
    params.append(limit)

    with _connect(profile) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def count_jobs(profile: str, **filters: Any) -> int:
    """Return count of jobs matching filters (same semantics as list_jobs, just count)."""
    # Simple path: use list_jobs with a big limit and count. Acceptable for volumes we expect.
    return len(list_jobs(profile, **filters))


def get_hot_companies(profile: str, days: int = 14, min_active_apps: int = 3) -> list[str]:
    """
    Return companies with >= min_active_apps active applications in the last N days.
    "Active" = state in (applied, responded, evaluated-with-submitted-date).
    Used by scan Phase 0 to pre-filter.
    """
    init_db(profile)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    with _connect(profile) as conn:
        rows = conn.execute(
            """
            SELECT company, COUNT(*) AS active_count
              FROM jobs
             WHERE profile_name = ?
               AND state IN ('applied', 'responded', 'interview')
               AND (applied_date >= ? OR updated_at >= ?)
             GROUP BY company
            HAVING COUNT(*) >= ?
            """,
            (profile, cutoff, cutoff, min_active_apps),
        ).fetchall()
        return [r["company"] for r in rows]


_SAFE_DISTINCT_COLUMNS = {
    "country", "mode", "company", "recommendation", "ats_source", "state",
}


def get_distinct_values(profile: str, column: str, with_counts: bool = True) -> list[tuple[str, int]]:
    """
    Return distinct non-null values for a column with row counts, sorted by count desc.
    Used by the UI to populate filter options dynamically from the DB so filters
    stay in sync with reality even as new countries / modes / companies are added.

    Returns [(value, count), ...]. If with_counts=False, count is always 0.
    """
    if column not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(f"Column '{column}' not allowed. Allowed: {sorted(_SAFE_DISTINCT_COLUMNS)}")
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute(
            f"""
            SELECT {column} AS v, COUNT(*) AS n
              FROM jobs
             WHERE profile_name = ? AND {column} IS NOT NULL AND {column} != ''
             GROUP BY {column}
             ORDER BY n DESC, v ASC
            """,
            (profile,),
        ).fetchall()
        return [(r["v"], r["n"]) for r in rows]


def get_stats(profile: str) -> dict[str, Any]:
    """Return summary stats: counts by state, average score, total applied, etc."""
    init_db(profile)
    with _connect(profile) as conn:
        stats: dict[str, Any] = {}
        for s in VALID_STATES:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE profile_name = ? AND state = ?",
                (profile, s),
            ).fetchone()
            stats[f"count_{s}"] = row["c"] if row else 0

        total_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM scan_runs WHERE profile_name = ?",
            (profile,),
        ).fetchone()
        stats["total_cost_usd"] = total_cost["c"] if total_cost else 0.0

        avg_score = conn.execute(
            "SELECT AVG(total_score) AS a FROM jobs WHERE profile_name = ? AND total_score IS NOT NULL",
            (profile,),
        ).fetchone()
        stats["avg_score"] = round(avg_score["a"], 2) if avg_score and avg_score["a"] else 0.0

        stats["hot_companies"] = get_hot_companies(profile)
    return stats


# ============================================================
# Dedup helper (used by Phase 2 during marathon)
# ============================================================

def existing_urls(profile: str) -> set[str]:
    """Return all URLs already stored for this profile. Used for cross-run dedup."""
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute(
            "SELECT url FROM jobs WHERE profile_name = ?",
            (profile,),
        ).fetchall()
        return {r["url"] for r in rows}


# ============================================================
# Queue integration (for /tailor --batch)
# ============================================================

def get_queued_for_tailor(profile: str) -> list[dict[str, Any]]:
    """Return jobs in 'queued_for_tailor' state, ready to tailor."""
    return list_jobs(profile, state="queued_for_tailor", order_by="total_score DESC")


def toggle_star(profile: str, job_id: int) -> bool:
    """
    Flip is_starred for a job. Returns the new state (True = starred).
    Used by the UI star button.
    """
    init_db(profile)
    with _connect(profile) as conn:
        row = conn.execute(
            "SELECT is_starred FROM jobs WHERE id = ? AND profile_name = ?",
            (job_id, profile),
        ).fetchone()
        if not row:
            raise ValueError(f"Job {job_id} not found for profile {profile}")
        new_val = 0 if row["is_starred"] else 1
        conn.execute("UPDATE jobs SET is_starred = ? WHERE id = ?", (new_val, job_id))
    return bool(new_val)


def mark_tailored(profile: str, job_id: int, *, cv_path: str, cover_path: str | None = None) -> None:
    """Mark a job as tailored. Updates paths and sets state to 'tailored'."""
    update_job(
        profile, job_id,
        state="tailored",
        cv_generated=1,
        cv_path=cv_path,
        cover_generated=1 if cover_path else 0,
        cover_path=cover_path,
    )


# ============================================================
# Link health (check URL still resolves)
# ============================================================

def _http_status(url: str, timeout: float = 8.0) -> int:
    """
    Return HTTP status for a URL. Uses HEAD with fallback to a tiny GET
    because some ATSes (Ashby, Lever) 405 on HEAD.

    Returns:
        - 200-599 on HTTP response
        - 0 on network error (DNS failure, timeout, connection reset)
    """
    import urllib.error
    import urllib.request

    # HEAD first (cheap). Some ATSes don't support it → fall back to GET.
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={
                "User-Agent": "Matchbox/1.0 (+link-health-check)",
                "Accept": "text/html,*/*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            # 405 on HEAD → retry with GET. Any other HTTP status → return it.
            if method == "HEAD" and e.code == 405:
                continue
            return e.code
        except urllib.error.URLError:
            return 0
        except Exception:
            return 0
    return 0


def check_url(profile: str, job_id: int) -> int:
    """
    Check a single job's URL, write status + timestamp to DB, return the status.
    Status 0 means network error; 200 means live; 404/410 means the posting is gone.
    """
    init_db(profile)
    with _connect(profile) as conn:
        row = conn.execute(
            "SELECT url FROM jobs WHERE id = ? AND profile_name = ?",
            (job_id, profile),
        ).fetchone()
        if not row:
            raise ValueError(f"Job {job_id} not found for profile {profile}")
        url = row["url"]

    status = _http_status(url)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(profile) as conn:
        conn.execute(
            "UPDATE jobs SET url_last_checked = ?, url_http_status = ? WHERE id = ?",
            (now, status, job_id),
        )
    return status


def bulk_check_urls(
    profile: str,
    job_ids: list[int] | None = None,
    *,
    stale_hours: int = 24,
    limit: int = 200,
) -> dict[str, int]:
    """
    Re-check URLs for a batch of jobs. Returns count summary:
        {"checked": N, "live": N, "dead": N, "error": N}

    If job_ids is None, re-checks jobs whose url_last_checked is NULL or older
    than stale_hours, capped at `limit`. This is the "refresh stale" path used
    by the UI's "Check all links" button.

    `dead` = HTTP 4xx/5xx. `error` = network failure (status 0). `live` = 2xx/3xx.
    """
    init_db(profile)
    if job_ids is None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat(timespec="seconds")
        with _connect(profile) as conn:
            rows = conn.execute(
                """
                SELECT id FROM jobs
                 WHERE profile_name = ?
                   AND state NOT IN ('applied', 'responded', 'interview', 'offer', 'rejected', 'discarded')
                   AND (url_last_checked IS NULL OR url_last_checked < ?)
                 ORDER BY total_score DESC
                 LIMIT ?
                """,
                (profile, cutoff, limit),
            ).fetchall()
            job_ids = [r["id"] for r in rows]

    summary = {"checked": 0, "live": 0, "dead": 0, "error": 0}
    for jid in job_ids:
        status = check_url(profile, jid)
        summary["checked"] += 1
        if status == 0:
            summary["error"] += 1
        elif 200 <= status < 400:
            summary["live"] += 1
        else:
            summary["dead"] += 1
    return summary


# ============================================================
# CLI smoke test
# ============================================================

if __name__ == "__main__":
    # Quick smoke test: create, insert, query, update. Useful for debugging.
    import sys

    profile = sys.argv[1] if len(sys.argv) > 1 else "_smoke_test"
    print(f"Smoke testing db.py with profile '{profile}'...")

    init_db(profile)
    print(f"  Schema initialised at: {db_path(profile)}")

    run_id = create_scan_run(profile, mode="dream", country="india", is_trial=True)
    print(f"  Created scan_run {run_id}")

    job_id = insert_job(
        profile_name=profile,
        run_id=run_id,
        company="TestCo",
        role="Test Role",
        url=f"https://example.com/{datetime.now(timezone.utc).timestamp()}",
        country="india",
        mode="dream",
        total_score=4.2,
        recommendation="APPLY",
    )
    print(f"  Inserted job {job_id}")

    jobs = list_jobs(profile, country="india", min_score=4.0)
    print(f"  Query returned {len(jobs)} jobs")

    update_job_state(profile, job_id, "queued_for_tailor", note="smoke test")
    print(f"  State transition OK")

    complete_scan_run(profile, run_id, scored_count=1, apply_count=1, cost_usd=0.001, status="success")
    stats = get_stats(profile)
    print(f"  Stats: {json.dumps(stats, indent=2)}")

    print("Smoke test passed.")
