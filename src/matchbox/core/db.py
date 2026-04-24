"""
SQLite access layer — the only file that contains SQL.

SSOT: every read/write of pipeline state goes through this module.
No other module imports sqlite3 directly.

Path convention (v0.2): people/{name}/db.sqlite
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from matchbox.core.exceptions import InvalidStateError
from matchbox.core.schema import VALID_STATES, Application, Job, ScanRun


# ──────────────────────────────────────────────
# Path resolution
# ──────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]  # src/matchbox/core/db.py → repo root


def db_path(profile: str) -> Path:
    return _repo_root() / "people" / profile / "db.sqlite"


# ──────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────

@contextmanager
def _connect(profile: str) -> Iterator[sqlite3.Connection]:
    path = db_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────

_SCHEMA_SQL = """
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
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name              TEXT NOT NULL,
    scan_run_id               INTEGER REFERENCES scan_runs(id),
    company                   TEXT NOT NULL,
    role                      TEXT NOT NULL,
    location                  TEXT,
    country                   TEXT,
    url                       TEXT NOT NULL,
    mode                      TEXT,
    ats_source                TEXT,
    posting_date              TEXT,
    discovered_date           TEXT NOT NULL,
    jd_summary                TEXT,
    jd_text                   TEXT,
    comp_stated               TEXT,
    visa_sponsorship          TEXT,
    legitimacy                TEXT,
    cv_match_score            REAL,
    company_mission_fit_score REAL,
    role_mission_fit_score    REAL,
    comp_score                REAL,
    cultural_score            REAL,
    red_flags_score           REAL,
    total_score               REAL,
    recommendation            TEXT,
    report_path               TEXT,
    state                     TEXT NOT NULL DEFAULT 'evaluated',
    tier                      TEXT,
    tailor_cost_usd           REAL,
    cv_generated              INTEGER DEFAULT 0,
    cover_generated           INTEGER DEFAULT 0,
    cv_path                   TEXT,
    cover_path                TEXT,
    applied_date              TEXT,
    response_date             TEXT,
    response_type             TEXT,
    response_note             TEXT,
    interview_notes           TEXT,
    rejection_reason          TEXT,
    user_notes                TEXT,
    is_starred                INTEGER DEFAULT 0,
    role_family               TEXT,
    exclusion_triggered       TEXT,
    dream_tier                TEXT,
    url_last_checked          TEXT,
    url_http_status           INTEGER,
    created_at                TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (profile_name, url)
);

CREATE INDEX IF NOT EXISTS idx_jobs_profile_state  ON jobs(profile_name, state);
CREATE INDEX IF NOT EXISTS idx_jobs_score          ON jobs(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company        ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_country        ON jobs(country);
CREATE INDEX IF NOT EXISTS idx_jobs_created        ON jobs(created_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs FOR EACH ROW BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS responses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    profile_name  TEXT NOT NULL,
    response_date TEXT NOT NULL,
    response_type TEXT NOT NULL,
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns to add if missing (forward-migration for existing DBs).
_JOBS_MIGRATIONS: list[tuple[str, str]] = [
    ("jd_text",                "TEXT"),
    ("tier",                   "TEXT"),
    ("tailor_cost_usd",        "REAL"),
    ("response_date",          "TEXT"),
    ("response_type",          "TEXT"),
    ("response_note",          "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, defn in _JOBS_MIGRATIONS:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {defn}")


def init_db(profile: str) -> None:
    """Idempotently create schema and run column migrations. Safe to call at every entry."""
    with _connect(profile) as conn:
        conn.executescript(_SCHEMA_SQL)
        _migrate(conn)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _assert_state(state: str) -> None:
    if state not in VALID_STATES:
        raise InvalidStateError(f"Invalid state '{state}'. Valid: {sorted(VALID_STATES)}")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _job_from_row(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["cv_generated"] = bool(d.get("cv_generated", 0))
    d["cover_generated"] = bool(d.get("cover_generated", 0))
    d["is_starred"] = bool(d.get("is_starred", 0))
    return Job.model_validate(d)


def _scan_run_from_row(row: sqlite3.Row) -> ScanRun:
    d = dict(row)
    d["is_trial"] = bool(d.get("is_trial", 0))
    return ScanRun.model_validate(d)


# ──────────────────────────────────────────────
# Scan runs
# ──────────────────────────────────────────────

def create_scan_run(
    profile: str,
    mode: str | None = None,
    country: str | None = None,
    is_trial: bool = False,
) -> int:
    init_db(profile)
    with _connect(profile) as conn:
        cursor = conn.execute(
            "INSERT INTO scan_runs (profile_name, mode, country, started_at, status, is_trial) "
            "VALUES (?, ?, ?, datetime('now'), 'running', ?)",
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
    with _connect(profile) as conn:
        conn.execute(
            "UPDATE scan_runs SET completed_at=datetime('now'), raw_candidates=?, "
            "filtered_survivors=?, scored_count=?, apply_count=?, review_count=?, "
            "skip_count=?, cost_usd=?, status=?, notes=? WHERE id=?",
            (raw_candidates, filtered_survivors, scored_count, apply_count,
             review_count, skip_count, cost_usd, status, notes, run_id),
        )


def get_scan_history(profile: str, limit: int = 20) -> list[ScanRun]:
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute(
            "SELECT * FROM scan_runs WHERE profile_name=? ORDER BY started_at DESC LIMIT ?",
            (profile, limit),
        ).fetchall()
        return [_scan_run_from_row(r) for r in rows]


# ──────────────────────────────────────────────
# Jobs — write
# ──────────────────────────────────────────────

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
    jd_text: str | None = None,
    comp_stated: str | None = None,
    visa_sponsorship: str | None = None,
    legitimacy: str | None = None,
    cv_match_score: float | None = None,
    company_mission_fit_score: float | None = None,
    role_mission_fit_score: float | None = None,
    comp_score: float | None = None,
    cultural_score: float | None = None,
    red_flags_score: float | None = None,
    total_score: float | None = None,
    recommendation: str | None = None,
    report_path: str | None = None,
    state: str = "evaluated",
    role_family: str | None = None,
    dream_tier: str | None = None,
    exclusion_triggered: str | None = None,
) -> int:
    _assert_state(state)
    init_db(profile_name)
    with _connect(profile_name) as conn:
        cursor = conn.execute(
            "INSERT INTO jobs ("
            "  profile_name, scan_run_id, company, role, url, discovered_date,"
            "  location, country, mode, ats_source, posting_date,"
            "  jd_summary, jd_text, comp_stated, visa_sponsorship, legitimacy,"
            "  cv_match_score, company_mission_fit_score, role_mission_fit_score,"
            "  comp_score, cultural_score, red_flags_score, total_score,"
            "  recommendation, report_path, state, role_family, dream_tier, exclusion_triggered"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_name, run_id, company, role, url,
             discovered_date or _today(),
             location, country, mode, ats_source, posting_date,
             jd_summary, jd_text, comp_stated, visa_sponsorship, legitimacy,
             cv_match_score, company_mission_fit_score, role_mission_fit_score,
             comp_score, cultural_score, red_flags_score, total_score,
             recommendation, report_path, state, role_family, dream_tier, exclusion_triggered),
        )
        return cursor.lastrowid or 0


def bulk_insert_jobs(
    profile_name: str,
    run_id: int | None,
    jobs: Iterable[dict[str, Any]],
    *,
    skip_duplicates: bool = True,
) -> tuple[int, int]:
    """Insert many jobs. Returns (inserted, skipped)."""
    init_db(profile_name)
    inserted = skipped = 0
    with _connect(profile_name) as conn:
        for j in jobs:
            state = j.get("state", "evaluated")
            _assert_state(state)
            try:
                conn.execute(
                    "INSERT INTO jobs ("
                    "  profile_name, scan_run_id, company, role, url, discovered_date,"
                    "  location, country, mode, ats_source, jd_summary, jd_text,"
                    "  total_score, state, role_family, dream_tier, exclusion_triggered"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (profile_name, run_id, j["company"], j["role"], j["url"],
                     j.get("discovered_date") or _today(),
                     j.get("location"), j.get("country"), j.get("mode"),
                     j.get("ats_source"), j.get("jd_summary"), j.get("jd_text"),
                     j.get("total_score"), state,
                     j.get("role_family"), j.get("dream_tier"), j.get("exclusion_triggered")),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                if skip_duplicates:
                    skipped += 1
                else:
                    raise
    return inserted, skipped


def update_job(profile: str, job_id: int, **fields: Any) -> None:
    if not fields:
        return
    if "state" in fields:
        _assert_state(fields["state"])
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [job_id]
    with _connect(profile) as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", vals)


def update_job_state(
    profile: str,
    job_id: int,
    new_state: str,
    note: str | None = None,
) -> None:
    _assert_state(new_state)
    with _connect(profile) as conn:
        if note:
            conn.execute(
                "UPDATE jobs SET state=?, user_notes=COALESCE(user_notes||' | '||?,?) WHERE id=?",
                (new_state, note, note, job_id),
            )
        else:
            conn.execute("UPDATE jobs SET state=? WHERE id=?", (new_state, job_id))
        if new_state == "applied":
            conn.execute(
                "UPDATE jobs SET applied_date=COALESCE(applied_date,date('now')) WHERE id=?",
                (job_id,),
            )


def mark_tailored(
    profile: str,
    job_id: int,
    *,
    cv_path: str,
    cover_path: str | None = None,
    tier: str,
    cost_usd: float = 0.0,
) -> None:
    update_job(
        profile, job_id,
        state="tailored",
        cv_generated=1,
        cv_path=cv_path,
        cover_generated=1 if cover_path else 0,
        cover_path=cover_path,
        tier=tier,
        tailor_cost_usd=cost_usd,
    )


def toggle_star(profile: str, job_id: int) -> bool:
    init_db(profile)
    with _connect(profile) as conn:
        row = conn.execute(
            "SELECT is_starred FROM jobs WHERE id=? AND profile_name=?", (job_id, profile)
        ).fetchone()
        if not row:
            raise ValueError(f"Job {job_id} not found for profile {profile}")
        new_val = 0 if row["is_starred"] else 1
        conn.execute("UPDATE jobs SET is_starred=? WHERE id=?", (new_val, job_id))
    return bool(new_val)


# ──────────────────────────────────────────────
# Jobs — read
# ──────────────────────────────────────────────

def get_job(profile: str, job_id: int) -> Job | None:
    init_db(profile)
    with _connect(profile) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id=? AND profile_name=?", (job_id, profile)
        ).fetchone()
        return _job_from_row(row) if row else None


_SAFE_ORDER = {
    "total_score DESC": "total_score DESC",
    "total_score ASC": "total_score ASC",
    "discovered_date DESC": "discovered_date DESC",
    "company ASC": "company ASC",
    "state ASC": "state ASC",
    "created_at DESC": "created_at DESC",
    "starred_first": "is_starred DESC, total_score DESC",
}

_SAFE_DISTINCT = {"country", "mode", "company", "recommendation", "ats_source", "state"}


def list_jobs(
    profile: str,
    *,
    state: str | list[str] | None = None,
    country: str | list[str] | None = None,
    mode: str | list[str] | None = None,
    dream_tier: str | list[str] | None = None,
    role_family: str | list[str] | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    is_starred: bool | None = None,
    company_search: str | None = None,
    role_search: str | None = None,
    since_date: str | None = None,
    limit: int = 1000,
    order_by: str = "total_score DESC",
) -> list[Job]:
    init_db(profile)
    where = ["profile_name=?"]
    params: list[Any] = [profile]

    def _in(col: str, val: str | list[str]) -> None:
        if isinstance(val, str):
            where.append(f"{col}=?")
            params.append(val)
        else:
            where.append(f"{col} IN ({','.join('?'*len(val))})")
            params.extend(val)

    if state is not None:
        _in("state", state)
    if country is not None:
        _in("country", country)
    if mode is not None:
        _in("mode", mode)
    if dream_tier is not None:
        _in("dream_tier", dream_tier)
    if role_family is not None:
        _in("role_family", role_family)
    if min_score is not None:
        where.append("total_score>=?")
        params.append(min_score)
    if max_score is not None:
        where.append("total_score<=?")
        params.append(max_score)
    if is_starred is not None:
        where.append("is_starred=?")
        params.append(1 if is_starred else 0)
    if company_search:
        where.append("LOWER(company) LIKE ?")
        params.append(f"%{company_search.lower()}%")
    if role_search:
        where.append("LOWER(role) LIKE ?")
        params.append(f"%{role_search.lower()}%")
    if since_date:
        where.append("discovered_date>=?")
        params.append(since_date)

    order = _SAFE_ORDER.get(order_by, "total_score DESC")
    params.append(limit)
    with _connect(profile) as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?",
            params,
        ).fetchall()
        return [_job_from_row(r) for r in rows]


def existing_urls(profile: str) -> set[str]:
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute("SELECT url FROM jobs WHERE profile_name=?", (profile,)).fetchall()
        return {r["url"] for r in rows}


def get_queued_for_tailor(profile: str) -> list[Job]:
    return list_jobs(profile, state="queued_for_tailor", order_by="total_score DESC")


def get_stats(profile: str) -> dict[str, Any]:
    init_db(profile)
    with _connect(profile) as conn:
        stats: dict[str, Any] = {}
        for s in VALID_STATES:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE profile_name=? AND state=?",
                (profile, s),
            ).fetchone()
            stats[f"count_{s}"] = row["c"] if row else 0
        cost_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) AS c FROM scan_runs WHERE profile_name=?",
            (profile,),
        ).fetchone()
        stats["total_cost_usd"] = cost_row["c"] if cost_row else 0.0
        avg_row = conn.execute(
            "SELECT AVG(total_score) AS a FROM jobs WHERE profile_name=? AND total_score IS NOT NULL",
            (profile,),
        ).fetchone()
        stats["avg_score"] = round(avg_row["a"], 2) if avg_row and avg_row["a"] else 0.0
    return stats


def get_distinct_values(profile: str, column: str) -> list[tuple[str, int]]:
    if column not in _SAFE_DISTINCT:
        raise ValueError(f"Column '{column}' not in allowlist. Allowed: {sorted(_SAFE_DISTINCT)}")
    init_db(profile)
    with _connect(profile) as conn:
        rows = conn.execute(
            f"SELECT {column} AS v, COUNT(*) AS n FROM jobs "
            f"WHERE profile_name=? AND {column} IS NOT NULL AND {column}!='' "
            f"GROUP BY {column} ORDER BY n DESC, v ASC",
            (profile,),
        ).fetchall()
        return [(r["v"], r["n"]) for r in rows]


# ──────────────────────────────────────────────
# Responses (outcome tracking)
# ──────────────────────────────────────────────

def log_response(
    profile: str,
    job_id: int,
    *,
    response_date: str,
    response_type: str,
    note: str | None = None,
) -> int:
    from matchbox.core.schema import VALID_RESPONSE_TYPES
    if response_type not in VALID_RESPONSE_TYPES:
        raise ValueError(f"Invalid response_type '{response_type}'")
    init_db(profile)
    with _connect(profile) as conn:
        cursor = conn.execute(
            "INSERT INTO responses (job_id, profile_name, response_date, response_type, note) "
            "VALUES (?,?,?,?,?)",
            (job_id, profile, response_date, response_type, note),
        )
        # Mirror on the job row for quick queries
        conn.execute(
            "UPDATE jobs SET response_date=?, response_type=?, response_note=? WHERE id=?",
            (response_date, response_type, note, job_id),
        )
        return cursor.lastrowid or 0


def get_responses(profile: str, job_id: int | None = None) -> list[dict[str, Any]]:
    init_db(profile)
    with _connect(profile) as conn:
        if job_id is not None:
            rows = conn.execute(
                "SELECT * FROM responses WHERE profile_name=? AND job_id=? ORDER BY response_date DESC",
                (profile, job_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM responses WHERE profile_name=? ORDER BY response_date DESC",
                (profile,),
            ).fetchall()
        return [dict(r) for r in rows]
