"""ingest_cli — write the brain's parsed library payload to the DB.

The brain reads files in `inbox/`, extracts components, and writes a JSON
file (conforming to schemas/ingest.v1.json). It then invokes this CLI:

    python -m matchbox.onboarding.ingest_cli --file path/to/payload.json

All rows land with `facts_verified = false`; the user confirms them in the
review screen. Tags are deduplicated against the existing tag table.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from matchbox.core import library as lib
from matchbox.core.db import connect, transaction
from matchbox.core.migrations import migrate
from matchbox.core.models import ItemType

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "ingest.v1.json"


def _load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _apply_tags(
    conn: sqlite3.Connection,
    *,
    item_type: ItemType,
    item_id: int,
    tags: list[dict[str, str]],
) -> None:
    for t in tags:
        lib.attach_tag(
            conn,
            item_type=item_type,
            item_id=item_id,
            facet=t["facet"],  # type: ignore[arg-type]
            value=t["value"],
        )


def _upsert_profile(conn: sqlite3.Connection, profile: dict[str, Any]) -> None:
    row = conn.execute("SELECT id FROM profile LIMIT 1").fetchone()
    links_json = json.dumps(profile.get("links", []))
    fields = {
        "full_name": profile.get("full_name", ""),
        "email": profile.get("email"),
        "phone": profile.get("phone"),
        "location": profile.get("location"),
        "links_json": links_json,
        "headline": profile.get("headline"),
    }
    if row is None:
        conn.execute(
            """
            INSERT INTO profile (full_name, email, phone, location, links_json, headline)
            VALUES (:full_name, :email, :phone, :location, :links_json, :headline)
            """,
            fields,
        )
    else:
        conn.execute(
            """
            UPDATE profile SET full_name = :full_name, email = :email, phone = :phone,
                               location = :location, links_json = :links_json,
                               headline = :headline
             WHERE id = :id
            """,
            {**fields, "id": row[0]},
        )


def ingest(payload: dict[str, Any], conn: sqlite3.Connection) -> dict[str, int]:
    """Apply the validated payload to the DB. Returns a counts summary."""
    counts: dict[str, int] = {
        "experiences": 0,
        "bullets": 0,
        "projects": 0,
        "skills": 0,
        "summaries": 0,
        "tags": 0,
    }

    with transaction(conn):
        if "profile" in payload:
            _upsert_profile(conn, payload["profile"])

        for exp_in in payload.get("experiences", []):
            exp = lib.add_experience(
                conn,
                company=exp_in["company"],
                role=exp_in["role"],
                start_date=exp_in.get("start_date"),
                end_date=exp_in.get("end_date"),
                location=exp_in.get("location"),
                sort_order=exp_in.get("sort_order", 0),
            )
            counts["experiences"] += 1

            for b_in in exp_in.get("bullets", []):
                b = lib.add_bullet(
                    conn,
                    experience_id=exp.id,
                    text=b_in["text"],
                    has_metric=b_in.get("has_metric", False),
                    facts_verified=False,
                    source_file=b_in.get("source_file"),
                )
                counts["bullets"] += 1
                tags = b_in.get("tags", [])
                _apply_tags(conn, item_type="bullet", item_id=b.id, tags=tags)
                counts["tags"] += len(tags)

        for p_in in payload.get("projects", []):
            p = lib.add_project(
                conn,
                name=p_in["name"],
                text=p_in["text"],
                url=p_in.get("url"),
                facts_verified=False,
            )
            counts["projects"] += 1
            tags = p_in.get("tags", [])
            _apply_tags(conn, item_type="project", item_id=p.id, tags=tags)
            counts["tags"] += len(tags)

        for s_in in payload.get("skills", []):
            try:
                s = lib.add_skill(
                    conn,
                    name=s_in["name"],
                    category=s_in.get("category"),
                    proficiency=s_in.get("proficiency"),
                )
            except sqlite3.IntegrityError:
                # Skill already exists; skip but still attach any new tags.
                row = conn.execute(
                    "SELECT id FROM skill WHERE lower(name) = lower(?)",
                    (s_in["name"],),
                ).fetchone()
                if row is None:
                    raise
                s = lib.get_skill(conn, row[0])
            else:
                counts["skills"] += 1
            tags = s_in.get("tags", [])
            _apply_tags(conn, item_type="skill", item_id=s.id, tags=tags)
            counts["tags"] += len(tags)

        for sm_in in payload.get("summaries", []):
            sm = lib.add_summary(conn, label=sm_in["label"], text=sm_in["text"])
            counts["summaries"] += 1
            tags = sm_in.get("tags", [])
            _apply_tags(conn, item_type="summary_variant", item_id=sm.id, tags=tags)
            counts["tags"] += len(tags)

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file", required=True, type=Path, help="JSON payload conforming to ingest.v1.json"
    )
    parser.add_argument("--db", type=Path, default=None, help="Override DB path (optional).")
    args = parser.parse_args(argv)

    try:
        payload_text = args.file.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {args.file}: {e}", file=sys.stderr)
        return 2

    validator = _load_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        for err in errors:
            loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"schema error at {loc}: {err.message}", file=sys.stderr)
        return 3

    conn = connect(args.db) if args.db else connect()
    try:
        migrate(conn)
        counts = ingest(payload, conn)
    finally:
        conn.close()

    summary = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    print(f"ingested: {summary or 'nothing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
