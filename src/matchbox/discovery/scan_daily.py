"""Daily ATS scan — probes KNOWN_SOURCES, scores, routes, inserts into DB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from matchbox.core import db
from matchbox.core.person import load_person
from matchbox.core.schema import Job, Person
from matchbox.discovery.ats_probe import probe
from matchbox.discovery.sources import ATSSource, KNOWN_SOURCES
from matchbox.scoring.exclusions import filter_by_exclusions
from matchbox.scoring.rubric import score_job
from matchbox.scoring.tier_router import infer_geo, route_job

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    run_id: int
    raw: int
    inserted: int
    skipped_dupe: int
    excluded: int
    profile: str


def run_daily_scan(
    profile: str,
    *,
    country: str | None = None,
    sources: list[ATSSource] | None = None,
    trial: bool = False,
    dry_run: bool = False,
) -> ScanResult:
    """
    Probe ATS boards, score jobs, insert new ones into the DB.

    Args:
        profile:  Person directory name (e.g. "shiva")
        country:  Filter KNOWN_SOURCES to this country only (e.g. "uk")
        sources:  Override source list; defaults to KNOWN_SOURCES
        trial:    Mark scan run as trial (non-production)
        dry_run:  Skip DB writes — useful for testing probe connectivity
    """
    person = load_person(profile)
    source_list = sources if sources is not None else _filter_sources(KNOWN_SOURCES, country)

    run_id = db.create_scan_run(profile, mode="daily", country=country, is_trial=trial)
    log.info("scan_run=%d profile=%s sources=%d", run_id, profile, len(source_list))

    raw_jobs: list[dict[str, Any]] = []
    for src in source_list:
        batch = probe(src)
        log.debug("source=%s/%s fetched=%d", src.name, src.company, len(batch))
        raw_jobs.extend(batch)

    allowed, excluded = filter_by_exclusions(person, raw_jobs)
    log.info("raw=%d excluded=%d allowed=%d", len(raw_jobs), len(excluded), len(allowed))

    scored = _score_and_route(allowed, person)

    if dry_run:
        log.info("dry_run — skipping DB writes (run_id=%d)", run_id)
        db.complete_scan_run(
            profile,
            run_id,
            raw_candidates=len(raw_jobs),
            filtered_survivors=len(allowed),
            scored_count=len(scored),
            status="dry_run",
        )
        return ScanResult(run_id, len(raw_jobs), 0, 0, len(excluded), profile)

    # Insert excluded jobs so we have a record (state="skip")
    _insert_batch(profile, run_id, excluded)

    inserted, dupes = db.bulk_insert_jobs(profile, run_id, scored)
    log.info("inserted=%d dupes=%d", inserted, dupes)

    db.complete_scan_run(
        profile,
        run_id,
        raw_candidates=len(raw_jobs),
        filtered_survivors=len(allowed),
        scored_count=len(scored),
        skip_count=len(excluded),
        status="success",
    )
    return ScanResult(run_id, len(raw_jobs), inserted, dupes, len(excluded), profile)


def _filter_sources(sources: list[ATSSource], country: str | None) -> list[ATSSource]:
    if not country:
        return sources
    c = country.lower()
    return [s for s in sources if not s.country or s.country.lower() == c]


def _score_and_route(jobs: list[dict[str, Any]], person: Person) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in jobs:
        placeholder = Job(
            profile_name=person.name,
            company=raw.get("company", ""),
            role=raw.get("role", ""),
            url=raw.get("url", ""),
            location=raw.get("location"),
            country=raw.get("country"),
            ats_source=raw.get("ats_source"),
            jd_text=raw.get("jd_text"),
        )
        scored_job = score_job(placeholder, person, jd_text=raw.get("jd_text", ""))
        tier = route_job(scored_job, person)
        geo = infer_geo(raw.get("country"))

        enriched = dict(raw)
        enriched.update(
            total_score=scored_job.total_score,
            cv_match_score=scored_job.cv_match_score,
            company_mission_fit_score=scored_job.company_mission_fit_score,
            role_mission_fit_score=scored_job.role_mission_fit_score,
            comp_score=scored_job.comp_score,
            cultural_score=scored_job.cultural_score,
            red_flags_score=scored_job.red_flags_score,
            tier=tier,
            mode=geo,
            state="evaluated",
        )
        out.append(enriched)
    return out


def _insert_batch(profile: str, run_id: int, jobs: list[dict[str, Any]]) -> None:
    if jobs:
        db.bulk_insert_jobs(profile, run_id, jobs)
