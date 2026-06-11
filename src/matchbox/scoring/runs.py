"""Build and persist a tailoring run.

A "run" is the unit the brain operates on. The user picks jobs in the
triage UI; this module:

1. Allocates a new `run_id` of the form YYYY-MM-DD-NNN, monotonic per day.
2. Inserts a `run` row and one `run_job` per selected job.
3. Flips each job.status to 'selected'.
4. Writes `runs/<run-id>/work-queue.json` validated against
   schemas/work-queue.v1.json.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from matchbox.contracts import schema_errors
from matchbox.core.db import PROJECT_ROOT, transaction

RUNS_DIR = PROJECT_ROOT / "runs"


@dataclass(slots=True)
class JobSelection:
    job_id: int
    want_cv: bool
    want_cover: bool


def _allocate_run_id(conn: sqlite3.Connection, today: str | None = None) -> str:
    """YYYY-MM-DD-NNN, monotonic within today."""
    today = today or datetime.now(UTC).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT id FROM run WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{today}-%",),
    ).fetchone()
    if row is None:
        return f"{today}-001"
    last = int(row[0].rsplit("-", 1)[1])
    return f"{today}-{last + 1:03d}"


def _resolve_profile_db(conn: sqlite3.Connection) -> str:
    """Return the path to the live DB, expressed relative to the repo root
    when possible (matches the schema's expectation).
    """
    path_str = os.environ.get("MATCHBOX_DB")
    if path_str:
        p = Path(path_str).expanduser().resolve()
    else:
        slug = os.environ.get("MATCHBOX_PROFILE", "demo")
        p = PROJECT_ROOT / "people" / slug / "matchbox.db"
    try:
        # as_posix so the path in work-queue.json uses forward slashes on every
        # OS (str() would emit backslashes on Windows and break the contract).
        return p.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(p)


def create_run(
    conn: sqlite3.Connection,
    *,
    selections: list[JobSelection],
    palette: str = "slate",
    font: str = "source-serif",
    today: str | None = None,
) -> tuple[str, Path]:
    """Create a run row, run_job rows, and write work-queue.json.

    Returns (run_id, work_queue_path).
    """
    if not selections:
        raise ValueError("create_run: at least one job selection required")

    run_id = _allocate_run_id(conn, today=today)
    out_dir = RUNS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    queue_jobs: list[dict[str, object]] = []
    with transaction(conn):
        conn.execute("INSERT INTO run (id, status) VALUES (?, 'queued')", (run_id,))
        for sel in selections:
            row = conn.execute(
                "SELECT id, company, title, jd_text, apply_url, url FROM job WHERE id = ?",
                (sel.job_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"job {sel.job_id} not found")
            conn.execute(
                """
                INSERT INTO run_job (run_id, job_id, want_cv, want_cover, palette, font)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sel.job_id,
                    int(sel.want_cv),
                    int(sel.want_cover),
                    palette,
                    font,
                ),
            )
            conn.execute("UPDATE job SET status = 'selected' WHERE id = ?", (sel.job_id,))
            queue_jobs.append(
                {
                    "job_id": row["id"],
                    "company": row["company"],
                    "title": row["title"],
                    "jd_text": row["jd_text"] or "",
                    "apply_url": row["apply_url"] or row["url"],
                    "want_cv": sel.want_cv,
                    "want_cover": sel.want_cover,
                    "palette": palette,
                    "font": font,
                }
            )

    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile_db": _resolve_profile_db(conn),
        "jobs": queue_jobs,
    }

    errors = schema_errors("work-queue.v1.json", payload)
    if errors:
        raise ValueError("work-queue.json failed schema validation: " + "; ".join(errors))

    out_path = out_dir / "work-queue.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return run_id, out_path
