"""jobreqs — save the brain's extracted JD requirements to the DB.

Invoked by the brain after it has extracted requirements from a JD:

    python -m matchbox.jobreqs save --job <job_id> --file <reqs.json>

Validates against schemas/job-requirements.v1.json. The cached payload
lives in `job.requirements_json` (+ requirements_model + requirements_jd_hash).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from matchbox.core.db import PROJECT_ROOT, connect, transaction
from matchbox.core.logging import configure_logging
from matchbox.core.migrations import migrate

SCHEMA_PATH = PROJECT_ROOT / "schemas" / "job-requirements.v1.json"


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def save_requirements(conn: sqlite3.Connection, job_id: int, payload: dict[str, object]) -> None:
    """Validate then upsert the requirements JSON onto the job row.

    If the payload includes a `job_id` and it does not match the CLI's
    --job, that is a hard error: a wrong-job file usually means the
    brain saved the right requirements against the wrong job. Earlier
    versions silently overwrote the field; that hid the mistake.
    """
    payload_job_id = payload.get("job_id")
    if payload_job_id is not None and payload_job_id != job_id:
        raise ValueError(
            f"job_id mismatch: --job {job_id} but payload says {payload_job_id}. "
            "Re-author the file or correct the --job argument."
        )
    if payload_job_id is None:
        # Tolerate omission only — a hand-edited file without the field.
        payload = {**payload, "job_id": job_id}
    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = "; ".join(
            f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        )
        raise ValueError(f"job-requirements.json failed schema validation: {msgs}")

    with transaction(conn):
        cur = conn.execute(
            """
            UPDATE job
               SET requirements_json = ?,
                   requirements_model = ?,
                   requirements_jd_hash = ?
             WHERE id = ?
            """,
            (
                json.dumps(payload),
                str(payload.get("model_version", "")),
                payload.get("jd_hash"),
                job_id,
            ),
        )
        if cur.rowcount == 0:
            raise LookupError(f"job {job_id} not found")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    save = sub.add_parser("save", help="save extracted requirements for a job")
    save.add_argument("--job", type=int, required=True, help="job id")
    save.add_argument("--file", type=Path, required=True, help="path to requirements JSON")
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
            save_requirements(conn, args.job, payload)
        except ValueError as e:
            print(f"schema error: {e}", file=sys.stderr)
            return 3
        except LookupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 4
    finally:
        conn.close()

    print(f"saved {len(payload.get('requirements', []))} requirements for job {args.job}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
