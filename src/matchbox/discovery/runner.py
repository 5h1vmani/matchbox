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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast

import httpx

from matchbox.core.db import transaction
from matchbox.discovery import enrich
from matchbox.discovery.aggregators import (
    AggregatorError,
    _looks_remote,
    poll_adzuna,
    poll_himalayas,
    poll_remotive,
)
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


def _row_params(source_id: int | None, j: JobRecord) -> dict[str, Any]:
    """INSERT params for one job, with Tier-2 enrichment + the dedup key.

    country/remote come off the JobRecord; the eligibility/seniority signals are
    deterministic regex reads of the title + JD (no LLM)."""
    rec = enrich.enrich_record(j.title, j.jd_text)
    return {
        "source": source_id,
        "company": j.company,
        "title": j.title,
        "location": j.location,
        "url": j.url,
        "apply_url": j.apply_url,
        "jd_text": j.jd_text,
        "posted_at": j.posted_at,
        "fetched_at": _now_iso(),
        "country": j.country,
        # ATS pollers leave remote=False; derive it from the JD text so an ATS
        # remote role is filterable like an aggregator one.
        "remote": 1 if (j.remote or _looks_remote(j.title, j.location, j.jd_text)) else 0,
        "dedup_key": enrich.dedup_key(j.url, j.company, j.title, j.location),
        "seniority": rec["seniority"],
        "min_years_exp": rec["min_years_exp"],
        "role_family": rec["role_family"],
        "sponsorship": rec["sponsorship"],
        "citizenship_required": rec["citizenship_required"],
        "clearance_required": rec["clearance_required"],
        "remote_scope": rec["remote_scope"],
        "salary_min": j.salary_min,
        "salary_max": j.salary_max,
        "salary_currency": j.salary_currency,
        "salary_period": j.salary_period,
        "employment_type": j.employment_type,
    }


def _upsert_jobs(conn: sqlite3.Connection, source_id: int | None, jobs: list[JobRecord]) -> int:
    """INSERT OR IGNORE by url. Returns number of new rows inserted.

    `source_id` is None for aggregator-sourced jobs (they are not rows in
    `ats_source`). country/remote come straight off the JobRecord so the
    inbox can filter on them.
    """
    if not jobs:
        return 0
    # Drop re-scraped postings the user already dismissed in discovery, so a
    # dead end never returns (dedupe: match on url, else company+title).
    from matchbox.discovery_api.repo import is_dismissed_duplicate

    jobs = [
        j
        for j in jobs
        if not is_dismissed_duplicate(conn, url=j.url, company=j.company, title=j.title)
    ]
    if not jobs:
        return 0
    cur = conn.executemany(
        """
        INSERT OR IGNORE INTO job (
            source, company, title, location, url, apply_url,
            jd_text, posted_at, fetched_at, status, country, remote,
            dedup_key, seniority, min_years_exp, role_family, sponsorship,
            citizenship_required, clearance_required, remote_scope,
            salary_min, salary_max, salary_currency, salary_period, employment_type
        ) VALUES (
            :source, :company, :title, :location, :url, :apply_url,
            :jd_text, :posted_at, :fetched_at, 'new', :country, :remote,
            :dedup_key, :seniority, :min_years_exp, :role_family, :sponsorship,
            :citizenship_required, :clearance_required, :remote_scope,
            :salary_min, :salary_max, :salary_currency, :salary_period, :employment_type
        )
        """,
        [_row_params(source_id, j) for j in jobs],
    )
    # Link the new rows to a company row (insert any newly-seen employer first).
    conn.execute(
        "INSERT OR IGNORE INTO company (name) SELECT DISTINCT company FROM job "
        "WHERE company_id IS NULL AND company IS NOT NULL AND trim(company) <> ''"
    )
    conn.execute(
        "UPDATE job SET company_id = (SELECT id FROM company WHERE company.name = job.company) "
        "WHERE company_id IS NULL"
    )
    return cur.rowcount


def backfill_enrichment(conn: sqlite3.Connection) -> int:
    """One-time pass: enrich jobs that predate Tier-2 (sponsorship still NULL).

    Idempotent -- enrichment always sets `sponsorship` to a non-null value, so a
    re-run skips already-enriched rows. Rows enriched before the `role_family`
    tagger existed have it NULL, so we also catch those. (dedup_key/company_id
    were filled by the 007 migration backfill.) Returns the number of rows
    enriched."""
    rows = conn.execute(
        "SELECT id, title, jd_text FROM job WHERE sponsorship IS NULL OR role_family IS NULL"
    ).fetchall()
    with transaction(conn):
        for r in rows:
            rec = enrich.enrich_record(r["title"], r["jd_text"])
            conn.execute(
                "UPDATE job SET seniority = ?, min_years_exp = ?, role_family = ?, "
                "sponsorship = ?, citizenship_required = ?, clearance_required = ?, "
                "remote_scope = ? WHERE id = ?",
                (
                    rec["seniority"],
                    rec["min_years_exp"],
                    rec["role_family"],
                    rec["sponsorship"],
                    rec["citizenship_required"],
                    rec["clearance_required"],
                    rec["remote_scope"],
                    r["id"],
                ),
            )
    return len(rows)


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


# ─── aggregators (query/region sources, stored with source = NULL) ─────


@dataclass(slots=True)
class AggregatorResult:
    name: str
    ok: bool
    inserted: int
    fetched: int
    error: str | None


def _run_aggregator(
    conn: sqlite3.Connection,
    name: str,
    fetch: Callable[[], list[JobRecord]],
) -> AggregatorResult:
    try:
        jobs = fetch()
    except AggregatorError as e:
        return AggregatorResult(name=name, ok=False, inserted=0, fetched=0, error=str(e.message))
    with transaction(conn):
        inserted = _upsert_jobs(conn, None, jobs)
    return AggregatorResult(name=name, ok=True, inserted=inserted, fetched=len(jobs), error=None)


def scan_aggregators(
    conn: sqlite3.Connection,
    *,
    client: httpx.Client | None = None,
    himalayas: bool = True,
    remotive: bool = True,
    adzuna: dict[str, Any] | None = None,
) -> list[AggregatorResult]:
    """Scan the no-auth remote aggregators (Himalayas, Remotive) and, when an
    Adzuna BYO-key config is supplied, Adzuna too. Aggregator jobs store with
    source = NULL (not ats_source rows) and carry country/remote.

    `adzuna` config shape:
        {"app_id": "...", "app_key": "...",
         "queries": [{"country": "in", "what": "...", "where": "..."}]}
    One failing source does not poison the others.
    """
    owned = client is None
    if client is None:
        client = httpx.Client()
    results: list[AggregatorResult] = []
    try:
        if himalayas:
            results.append(
                _run_aggregator(conn, "himalayas", lambda: poll_himalayas(client=client))
            )
        if remotive:
            results.append(_run_aggregator(conn, "remotive", lambda: poll_remotive(client=client)))
        if adzuna and adzuna.get("app_id") and adzuna.get("app_key"):
            app_id = str(adzuna["app_id"])
            app_key = str(adzuna["app_key"])
            for q in adzuna.get("queries") or [{"country": "in"}]:
                country = str(q.get("country", "in"))
                what = str(q.get("what", ""))
                where = str(q.get("where", ""))
                label = f"adzuna:{country}" + (f":{what}" if what else "")
                fetch = partial(
                    poll_adzuna,
                    app_id=app_id,
                    app_key=app_key,
                    client=client,
                    country=country,
                    what=what,
                    where=where,
                )
                results.append(_run_aggregator(conn, label, fetch))
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
