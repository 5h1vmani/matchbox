"""Artifact CLI -- save and inspect generated outputs.

    python -m matchbox.artifacts save --app 5 --kind prep --body "Prep brief..."
    python -m matchbox.artifacts save --app 5 --kind cv --path /tmp/cv.pdf --final
    python -m matchbox.artifacts save --app 5 --kind followup --file followup.txt
    python -m matchbox.artifacts list --app 5
    python -m matchbox.artifacts list --app 5 --kind cv
    python -m matchbox.artifacts sent --id 3

Every command prints JSON to stdout. The DB is chosen by MATCHBOX_DB /
MATCHBOX_PROFILE (same resolution as the rest of matchbox).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from matchbox.artifacts import repo
from matchbox.core.db import connect
from matchbox.core.migrations import migrate


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="matchbox.artifacts",
        description="Artifact storage: save and inspect generated outputs.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # ── save ──────────────────────────────────────────────────────────────────
    ps = sub.add_parser("save", help="Store a new artifact.")
    ps.add_argument("--app", type=int, required=True, metavar="N", help="Application id.")
    ps.add_argument(
        "--kind",
        required=True,
        choices=repo.VALID_KINDS,
        help="Artifact kind.",
    )
    src = ps.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path, default=None, help="Read text body from a file.")
    src.add_argument("--body", default=None, help="Inline text body.")
    src.add_argument(
        "--path", default=None, help="Filesystem path to a file artifact (e.g. cv.pdf)."
    )
    ps.add_argument(
        "--final",
        action="store_true",
        default=False,
        help="Set status=final (default: draft).",
    )

    # ── list ──────────────────────────────────────────────────────────────────
    pl = sub.add_parser("list", help="List artifacts for an application.")
    pl.add_argument("--app", type=int, required=True, metavar="N", help="Application id.")
    pl.add_argument("--kind", default=None, choices=repo.VALID_KINDS, help="Filter by kind.")

    # ── sent ──────────────────────────────────────────────────────────────────
    pse = sub.add_parser("sent", help="Mark an artifact as sent.")
    pse.add_argument("--id", type=int, required=True, metavar="N", help="Artifact id.")

    args = p.parse_args(argv)
    conn = connect()
    migrate(conn)
    try:
        if args.cmd == "save":
            body: str | None = None
            path: str | None = None

            if args.file is not None:
                body = args.file.read_text(encoding="utf-8")
            elif args.body is not None:
                body = args.body
            else:
                # --path stores a filesystem path string into `path`
                path = args.path

            status = "final" if args.final else "draft"
            artifact_id = repo.create(
                conn,
                args.app,
                args.kind,
                path=path,
                body=body,
                status=status,
            )
            result = repo.get(conn, artifact_id)
            if result is None:
                print(f"error: artifact {artifact_id} not found after insert", file=sys.stderr)
                return 1
            _emit(result)

        elif args.cmd == "list":
            _emit(repo.list_for_app(conn, args.app, kind=args.kind))

        elif args.cmd == "sent":
            updated = repo.set_status(conn, args.id, "sent")
            if updated is None:
                print(f"no such artifact: {args.id}", file=sys.stderr)
                return 1
            _emit(updated)

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
