"""Offer CLI — manage received offers and run salary benchmarks.

    python -m matchbox.offers add --app 7 --base 120000 --currency USD
    python -m matchbox.offers list
    python -m matchbox.offers list --app 7
    python -m matchbox.offers status --id 3 --status accepted
    python -m matchbox.offers benchmark --base 120000 --currency USD

Every command prints JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.offers import repo
from matchbox.offers.benchmark import benchmark


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="matchbox.offers", description="Offer management.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # add
    pa = sub.add_parser("add", help="Record a new offer.")
    pa.add_argument("--app", type=int, required=True, help="Application id.")
    pa.add_argument("--base", type=float, default=None, help="Base salary.")
    pa.add_argument("--bonus", type=float, default=None, help="Bonus amount.")
    pa.add_argument("--equity", default=None, help="Equity description.")
    pa.add_argument("--currency", default=None, help="ISO 4217 currency code.")
    pa.add_argument("--location", default=None, help="Work location.")
    pa.add_argument("--received-at", dest="received_at", default=None, help="ISO date received.")
    pa.add_argument("--notes", default=None, help="Free-text notes.")

    # list
    pl = sub.add_parser("list", help="List offers.")
    pl.add_argument("--app", type=int, default=None, help="Filter by application id.")

    # status
    ps = sub.add_parser("status", help="Update offer status.")
    ps.add_argument("--id", type=int, required=True, help="Offer id.")
    ps.add_argument(
        "--status",
        required=True,
        choices=list(repo.VALID_STATUSES),
        help="New status.",
    )

    # benchmark
    pb = sub.add_parser("benchmark", help="Benchmark a base salary against your job pool.")
    pb.add_argument("--base", type=float, required=True, help="Base salary to benchmark.")
    pb.add_argument(
        "--role-family", dest="role_family", default=None, help="Filter by role family."
    )
    pb.add_argument("--currency", default=None, help="Filter by currency.")

    args = p.parse_args(argv)
    conn = connect()
    migrate(conn)

    try:
        if args.cmd == "add":
            oid = repo.create(
                conn,
                args.app,
                base=args.base,
                bonus=args.bonus,
                equity=args.equity,
                currency=args.currency,
                location=args.location,
                received_at=args.received_at,
                notes=args.notes,
            )
            _emit(repo.get(conn, oid))

        elif args.cmd == "list":
            if args.app is not None:
                _emit(repo.list_for_app(conn, args.app))
            else:
                _emit(repo.list_all(conn))

        elif args.cmd == "status":
            offer = repo.set_status(conn, args.id, args.status)
            if offer is None:
                print(f"no such offer: {args.id}", file=sys.stderr)
                return 1
            _emit(offer)

        elif args.cmd == "benchmark":
            _emit(
                benchmark(
                    conn,
                    base=args.base,
                    role_family=args.role_family,
                    currency=args.currency,
                )
            )

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
