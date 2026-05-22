"""Discovery runner — single scan-all entry point.

For each enabled `ats_source` row:
1. Call the matching poller with 3 tries and exponential backoff (1s, 4s, 16s).
2. On success: upsert jobs (INSERT OR IGNORE by url), update `last_ok_at`.
3. On failure: record `last_error`, leave existing jobs in place.

Failures are visible: a failed source surfaces with a populated
`last_error`, distinct from "no new jobs" which leaves it None.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from matchbox.core.db import transaction
from matchbox.discovery.base import AtsType, JobRecord, PollerError
from matchbox.discovery.pollers import POLLERS

log = logging.getLogger("matchbox.discovery")

DEFAULT_BACKOFF_SECONDS = (1.0, 4.0, 16.0)


@dataclass(slots=True)
class SourceResult:
    source_id: int
    ats_type: AtsType
    slug: str
    company: str
    ok: bool
    inserted: int
    fetched: int
    error: str | None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%fZ")


def _list_enabled_sources(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, ats_type, slug, company, country, sector
          FROM ats_source
         WHERE enabled = 1
         ORDER BY company, slug
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _upsert_jobs(conn: sqlite3.Connection, source_id: int, jobs: list[JobRecord]) -> int:
    """INSERT OR IGNORE by url. Returns number of new rows inserted."""
    if not jobs:
        return 0
    cur = conn.executemany(
        """
        INSERT OR IGNORE INTO job (
            source, company, title, location, url, apply_url,
            jd_text, posted_at, fetched_at, status
        ) VALUES (
            :source, :company, :title, :location, :url, :apply_url,
            :jd_text, :posted_at, :fetched_at, 'new'
        )
        """,
        [
            {
                "source": source_id,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "url": j.url,
                "apply_url": j.apply_url,
                "jd_text": j.jd_text,
                "posted_at": j.posted_at,
                "fetched_at": _now_iso(),
            }
            for j in jobs
        ],
    )
    return cur.rowcount


def _call_with_backoff(
    *,
    ats_type: AtsType,
    slug: str,
    company: str,
    client: httpx.Client,
    backoff: tuple[float, ...],
    sleep: object = time.sleep,
) -> list[JobRecord]:
    poller = POLLERS.get(ats_type)
    if poller is None:
        raise PollerError(ats_type, slug, f"no poller implemented for {ats_type}")
    last_err: PollerError | None = None
    for attempt, delay in enumerate(backoff, start=1):
        try:
            return poller(slug, company, client)
        except PollerError as e:
            last_err = e
            log.warning(
                "poll %s/%s failed (attempt %d/%d): %s",
                ats_type,
                slug,
                attempt,
                len(backoff),
                e.message,
            )
            if attempt < len(backoff):
                sleep(delay)  # type: ignore[operator]
    assert last_err is not None
    raise last_err


def scan_source(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    *,
    client: httpx.Client,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep: object = time.sleep,
) -> SourceResult:
    """Scan one source. Always updates last_attempt_at; success path also
    updates last_ok_at; failure path stores last_error."""
    ats_type = cast(AtsType, source["ats_type"])
    slug = str(source["slug"])
    company = str(source["company"])
    source_id = int(source["id"])

    try:
        jobs = _call_with_backoff(
            ats_type=ats_type,
            slug=slug,
            company=company,
            client=client,
            backoff=backoff,
            sleep=sleep,
        )
    except PollerError as e:
        with transaction(conn):
            conn.execute(
                "UPDATE ats_source SET last_attempt_at = ?, last_error = ? WHERE id = ?",
                (_now_iso(), str(e.message), source_id),
            )
        return SourceResult(
            source_id=source_id,
            ats_type=ats_type,
            slug=slug,
            company=company,
            ok=False,
            inserted=0,
            fetched=0,
            error=str(e.message),
        )

    with transaction(conn):
        inserted = _upsert_jobs(conn, source_id, jobs)
        conn.execute(
            "UPDATE ats_source SET last_attempt_at = ?, last_ok_at = ?, last_error = NULL WHERE id = ?",
            (_now_iso(), _now_iso(), source_id),
        )
    return SourceResult(
        source_id=source_id,
        ats_type=ats_type,
        slug=slug,
        company=company,
        ok=True,
        inserted=inserted,
        fetched=len(jobs),
        error=None,
    )


def scan_all(
    conn: sqlite3.Connection,
    *,
    client: httpx.Client | None = None,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep: object = time.sleep,
) -> list[SourceResult]:
    """Scan every enabled source. Caller owns the connection; we do the
    transactions ourselves per-source so one bad source does not poison
    the whole scan."""
    owned = client is None
    if client is None:
        client = httpx.Client()
    try:
        sources = _list_enabled_sources(conn)
        results: list[SourceResult] = []
        for src in sources:
            results.append(scan_source(conn, src, client=client, backoff=backoff, sleep=sleep))
        return results
    finally:
        if owned:
            client.close()


def probe(
    ats_type: AtsType,
    slug: str,
    company: str,
    *,
    client: httpx.Client | None = None,
) -> list[JobRecord]:
    """Probe a single (ats_type, slug) without DB writes — used by the
    add-source UI to verify a slug works before saving it."""
    poller = POLLERS.get(ats_type)
    if poller is None:
        raise PollerError(ats_type, slug, f"no poller implemented for {ats_type}")
    owned = client is None
    if client is None:
        client = httpx.Client()
    try:
        return poller(slug, company, client)
    finally:
        if owned:
            client.close()
