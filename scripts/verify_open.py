"""Render-based "verify still open" freshness check for matchbox job tracker.

Renders job URLs via headless Chrome, parses deadline/closed signals,
and updates application status when jobs are no longer accepting applications.

Subcommands:
  verify --job <id>        check if a single job is still open
  verify-active [--mark]   check all active applications, optionally mark closed ones
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from typing import Any

from matchbox.core.db import connect, transaction  # type: ignore[import-untyped]


def verify_open(url: str, *, timeout: int = 30) -> tuple[str, str]:
    """Render a job URL and extract its open/closed status.

    Returns a tuple (verdict, reason) where verdict is one of:
    - "open": job is accepting applications
    - "closed": job is no longer accepting applications
    - "unknown": could not determine status

    The reason contains the parsed deadline, matched phrase, or error message.
    """
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cmd = [
        chrome_path,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--dump-dom",
        "--virtual-time-budget=7000",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        html = result.stdout
    except subprocess.TimeoutExpired:
        return ("unknown", "render failed")
    except Exception:
        return ("unknown", "render failed")

    if not html or not html.strip():
        return ("unknown", "render failed")

    # Strip HTML tags and collapse whitespace
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    # Check for deadline pattern: "Deadline to Apply <DATE>"
    deadline_match = re.search(
        r"Deadline to Apply\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if deadline_match:
        date_str = deadline_match.group(1)
        try:
            # Try full month name first
            parsed_date = datetime.strptime(date_str, "%B %d, %Y").date()
        except ValueError:
            try:
                # Try abbreviated month name
                parsed_date = datetime.strptime(date_str, "%b %d, %Y").date()
            except ValueError:
                return ("unknown", f"deadline found but unparsed: {date_str}")

        today = date.today()
        if parsed_date < today:
            return ("closed", f"deadline passed: {date_str}")
        else:
            return ("open", f"deadline {date_str}")

    # Check for closed phrases (case-insensitive)
    closed_phrases = [
        "no longer accepting applications",
        "position is no longer",
        "applications are closed",
        "this job is closed",
        "this posting is closed",
        "this role is closed",
    ]
    for phrase in closed_phrases:
        if phrase.lower() in text.lower():
            return ("closed", phrase)

    return ("open", "")


def cmd_verify(job_id: int) -> None:
    """Check if a single job is still open."""
    c = connect()
    row = c.execute(
        "SELECT id, company, url FROM job WHERE id = ?",
        (job_id,),
    ).fetchone()
    c.close()

    if not row:
        print(f"{job_id} [not found]", file=sys.stderr)
        return

    job_id_val = row["id"]
    company = row["company"]
    url = row["url"]

    verdict, reason = verify_open(url)
    if reason:
        print(f"{job_id_val} {company} -> {verdict} | {reason}")
    else:
        print(f"{job_id_val} {company} -> {verdict}")


def cmd_verify_active(mark: bool) -> None:
    """Check all active applications and optionally mark closed ones as withdrawn."""
    c = connect()
    rows = c.execute(
        """
        SELECT
            a.id as app_id,
            j.id as job_id,
            j.company,
            j.url,
            a.status
        FROM application a
        JOIN job j ON a.job_id = j.id
        WHERE a.status NOT IN ('rejected', 'withdrawn', 'offer')
        ORDER BY j.id DESC
        """
    ).fetchall()
    c.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        job_id = row["job_id"]
        company = row["company"]
        url = row["url"]
        status = row["status"]
        verdict, reason = verify_open(url)
        results.append(
            {
                "job_id": job_id,
                "company": company,
                "status": status,
                "verdict": verdict,
                "reason": reason,
            }
        )

    # Print table
    print(
        "{:<8} {:<30} {:<12} {:<8} {:<40}".format(
            "job_id", "company", "status", "verdict", "reason"
        )
    )
    print("-" * 100)
    for r in results:
        print(
            "{:<8} {:<30} {:<12} {:<8} {:<40}".format(
                r["job_id"],
                r["company"][:29],
                r["status"],
                r["verdict"],
                r["reason"][:39],
            )
        )

    # Mark closed ones if requested
    if mark:
        c = connect()
        marked = 0
        with transaction(c):
            for r in results:
                if r["verdict"] == "closed":
                    app_id_to_mark = None
                    # Find the app_id for this job
                    for row in rows:
                        if row["job_id"] == r["job_id"]:
                            app_id_to_mark = row["app_id"]
                            break

                    if app_id_to_mark is not None:
                        # Get current notes
                        app_row = c.execute(
                            "SELECT notes FROM application WHERE id = ?",
                            (app_id_to_mark,),
                        ).fetchone()
                        current_notes = app_row["notes"] if app_row["notes"] else ""
                        new_notes = (
                            current_notes + f" Auto-closed: {r['reason']}"
                            if current_notes
                            else f"Auto-closed: {r['reason']}"
                        )

                        c.execute(
                            "UPDATE application SET status = 'withdrawn', notes = ? WHERE id = ?",
                            (new_notes, app_id_to_mark),
                        )
                        marked += 1

        c.close()
        print(f"\nMarked {marked} applications as withdrawn")


def main() -> int:
    """Parse arguments and dispatch to subcommands."""
    ap = argparse.ArgumentParser(
        description="Verify job posting freshness via headless browser render"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # verify --job <id>
    verify_parser = sub.add_parser("verify", help="Check a single job")
    verify_parser.add_argument("--job", type=int, required=True, help="Job ID to check")

    # verify-active [--mark]
    active_parser = sub.add_parser(
        "verify-active", help="Check all active applications"
    )
    active_parser.add_argument(
        "--mark",
        action="store_true",
        help="Mark closed applications as withdrawn",
    )

    args = ap.parse_args()

    if args.cmd == "verify":
        cmd_verify(args.job)
    elif args.cmd == "verify-active":
        cmd_verify_active(args.mark)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
