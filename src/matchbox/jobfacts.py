"""jobfacts — save the brain's precise job facts onto the job row.

The discovery scan's Tier-1 enrichment is coarse regex (good enough to filter
and rank thousands). For the shortlist worth pursuing, the brain reads the full
JD and saves precise facts:

    python -m matchbox.jobfacts save --job <job_id> --file <facts.json>

Validates against schemas/job-facts.v1.json (generated from
matchbox.contracts.JobFacts). PARTIAL update by design: only keys present in
the payload are written, so an omitted field keeps its scan-time value. Facts
must come from the JD text -- the brain never guesses (same no-fabrication rule
as everywhere else).

Exit codes mirror jobreqs: 0 ok, 2 unreadable/invalid JSON file, 3 schema
error, 4 job not found.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from matchbox.contracts import schema_errors
from matchbox.core.db import connect, transaction
from matchbox.core.logging import configure_logging
from matchbox.core.migrations import migrate

# Payload keys that map 1:1 onto job columns. schema_version/job_id are
# envelope, not facts.
_FACT_COLUMNS = (
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "employment_type",
    "seniority",
    "min_years_exp",
    "role_family",
    "remote_scope",
    "country",
    "sponsorship",
    "citizenship_required",
    "clearance_required",
    "closes_at",
)


def save_facts(conn: sqlite3.Connection, job_id: int, payload: dict[str, object]) -> list[str]:
    """Validate then write the supplied facts onto the job row. Returns the
    column names written.

    A payload job_id that contradicts --job is a hard error (same rule as
    jobreqs: a wrong-job file usually means right facts, wrong job). Keys
    absent from the payload are not touched; an explicit null clears the
    column (the brain saying "the JD does not state this").
    """
    payload_job_id = payload.get("job_id")
    if payload_job_id is not None and payload_job_id != job_id:
        raise ValueError(
            f"job_id mismatch: --job {job_id} but payload says {payload_job_id}. "
            "Re-author the file or correct the --job argument."
        )
    if payload_job_id is None:
        payload = {**payload, "job_id": job_id}
    errors = schema_errors("job-facts.v1.json", payload)
    if errors:
        raise ValueError("job-facts.json failed schema validation: " + "; ".join(errors))

    cols = [c for c in _FACT_COLUMNS if c in payload]
    if not cols:
        raise ValueError("payload carries no fact fields (nothing to save)")
    booleans = {"citizenship_required", "clearance_required"}
    values = [
        (None if payload[c] is None else (1 if payload[c] else 0)) if c in booleans else payload[c]
        for c in cols
    ]
    with transaction(conn):
        cur = conn.execute(
            f"UPDATE job SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
            (*values, job_id),
        )
        if cur.rowcount == 0:
            raise LookupError(f"job {job_id} not found")
    return cols


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    save = sub.add_parser("save", help="save precise job facts for a job")
    save.add_argument("--job", type=int, required=True, help="job id")
    save.add_argument("--file", type=Path, required=True, help="path to job-facts JSON")
    save.add_argument("--db", type=Path, default=None, help="override DB path")

    args = parser.parse_args(argv)

    try:
        text = args.file.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {args.file}: {e}", file=sys.stderr)
        return 2

    conn = connect(args.db) if args.db else connect()
    try:
        migrate(conn)
        try:
            written = save_facts(conn, args.job, payload)
        except ValueError as e:
            print(f"schema error: {e}", file=sys.stderr)
            return 3
        except LookupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 4
    finally:
        conn.close()

    print(f"saved {len(written)} facts for job {args.job}: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
