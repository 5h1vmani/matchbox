"""Agent-task queue CLI -- how the user's agent drains the work queue.

    python -m matchbox.agent_tasks list                 # pending tasks (JSON)
    python -m matchbox.agent_tasks list --all            # every state
    python -m matchbox.agent_tasks claim --id 12
    python -m matchbox.agent_tasks complete --id 12 --result out.json
    python -m matchbox.agent_tasks fail --id 12 --error "no JD text"
    python -m matchbox.agent_tasks enqueue --kind prep --app 5

Every command prints JSON to stdout (the agent parses it). The queue lives in
the active profile's DB (selected by MATCHBOX_DB / MATCHBOX_PROFILE).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from matchbox.agent_tasks import repo
from matchbox.core.db import connect
from matchbox.core.migrations import migrate


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="matchbox.agent_tasks", description="Agent-task queue.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="List tasks (default: pending).")
    pl.add_argument("--state", default="pending", help="Filter by state.")
    pl.add_argument("--kind", default=None, help="Filter by kind.")
    pl.add_argument("--all", action="store_true", help="All states (ignore --state).")

    pc = sub.add_parser("claim", help="Claim a pending task.")
    pc.add_argument("--id", type=int, required=True)

    pco = sub.add_parser("complete", help="Mark a task done.")
    pco.add_argument("--id", type=int, required=True)
    pco.add_argument("--result", type=Path, default=None, help="JSON file with the result.")

    pf = sub.add_parser("fail", help="Mark a task failed.")
    pf.add_argument("--id", type=int, required=True)
    pf.add_argument("--error", required=True)

    pe = sub.add_parser("enqueue", help="Add a task.")
    pe.add_argument("--kind", required=True)
    pe.add_argument("--job", type=int, default=None, help="Job id ref.")
    pe.add_argument("--app", type=int, default=None, help="Application id ref.")
    pe.add_argument("--payload", type=Path, default=None, help="JSON file with the payload.")

    args = p.parse_args(argv)
    conn = connect()
    migrate(conn)
    try:
        if args.cmd == "list":
            state = None if args.all else args.state
            _emit(repo.list_tasks(conn, state=state, kind=args.kind))
        elif args.cmd == "claim":
            task = repo.claim(conn, args.id)
            if task is None:
                print(f"no such task: {args.id}", file=sys.stderr)
                return 1
            _emit(task)
        elif args.cmd == "complete":
            result = json.loads(args.result.read_text(encoding="utf-8")) if args.result else None
            task = repo.complete(conn, args.id, result=result)
            if task is None:
                print(f"no such task: {args.id}", file=sys.stderr)
                return 1
            _emit(task)
        elif args.cmd == "fail":
            task = repo.fail(conn, args.id, args.error)
            if task is None:
                print(f"no such task: {args.id}", file=sys.stderr)
                return 1
            _emit(task)
        elif args.cmd == "enqueue":
            payload = json.loads(args.payload.read_text(encoding="utf-8")) if args.payload else None
            tid = repo.enqueue(
                conn, args.kind, job_id=args.job, application_id=args.app, payload=payload
            )
            _emit(repo.get(conn, tid))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
