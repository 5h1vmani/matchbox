"""Funding scan — probe recently funded companies not yet in KNOWN_SOURCES.

Usage pattern:
    companies = [
        {"name": "Embra", "ats": "ashby", "slug": "embra", "country": "us", "sector": "ai"},
        {"name": "Granola", "ats": "ashby", "slug": "granola-ai", "country": "uk", "sector": "ai"},
    ]
    results = probe_funded_companies(companies, profile="shiva")
"""

from __future__ import annotations

import logging
from typing import Any

from matchbox.core import db
from matchbox.core.person import load_person
from matchbox.discovery.ats_probe import probe
from matchbox.discovery.sources import ATSSource, ashby, greenhouse, lever, source_for_company
from matchbox.scoring.exclusions import filter_by_exclusions
from matchbox.scoring.rubric import score_job
from matchbox.scoring.tier_router import infer_geo, route_job
from matchbox.core.schema import Job

log = logging.getLogger(__name__)

# ATS factory map — keyed by the "ats" field in a company dict
_ATS_FACTORY = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
}


def probe_funded_companies(
    companies: list[dict[str, Any]],
    profile: str,
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Probe a list of recently-funded companies not yet in KNOWN_SOURCES.

    Each company dict supports these keys:
        name    (required)  — display name
        ats     (optional)  — "greenhouse"|"ashby"|"lever"; falls back to KNOWN_SOURCES lookup
        slug    (optional)  — ATS slug; required if ats is set
        country (optional)  — "uk"|"india"|"us" etc.
        sector  (optional)  — sector tag for exclusion checks

    Returns normalized, scored, enriched job dicts (same shape as scan_daily).
    Inserts results into DB unless dry_run=True.
    """
    person = load_person(profile)
    sources = _resolve_sources(companies)
    if not sources:
        log.warning("No resolvable ATS sources from %d company entries", len(companies))
        return []

    raw_jobs: list[dict[str, Any]] = []
    for src in sources:
        batch = probe(src)
        log.info("funding_probe company=%s fetched=%d", src.company, len(batch))
        raw_jobs.extend(batch)

    if not raw_jobs:
        return []

    allowed, excluded = filter_by_exclusions(person, raw_jobs)
    scored = _score_batch(allowed, person)
    all_jobs = excluded + scored

    if not dry_run:
        run_id = db.create_scan_run(profile, mode="funding", is_trial=False)
        db.bulk_insert_jobs(profile, run_id, all_jobs)
        db.complete_scan_run(
            profile,
            run_id,
            raw_candidates=len(raw_jobs),
            filtered_survivors=len(allowed),
            scored_count=len(scored),
            skip_count=len(excluded),
            status="success",
        )

    return all_jobs


def _resolve_sources(companies: list[dict[str, Any]]) -> list[ATSSource]:
    """Convert company dicts to ATSSources, falling back to KNOWN_SOURCES lookup."""
    sources: list[ATSSource] = []
    for c in companies:
        name = c.get("name", "")
        ats = c.get("ats", "").lower()
        slug = c.get("slug", "")
        country = c.get("country", "")
        sector = c.get("sector", "")

        if ats and slug and ats in _ATS_FACTORY:
            src = _ATS_FACTORY[ats](slug, name, country=country, sector=sector)
            sources.append(src)
            continue

        # Fall back to KNOWN_SOURCES lookup
        known = source_for_company(name)
        if known:
            sources.append(known)
            log.debug("resolved %s via KNOWN_SOURCES", name)
        else:
            log.warning("Cannot resolve ATS for '%s' — provide 'ats' and 'slug'", name)

    return sources


def _score_batch(jobs: list[dict[str, Any]], person: Any) -> list[dict[str, Any]]:
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
