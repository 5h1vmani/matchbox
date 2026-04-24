"""ATS API probers — Greenhouse, Ashby, Lever. Returns normalized job dicts."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from matchbox.discovery.sources import ATSSource

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Matchbox/0.2 job-scan"}
_TIMEOUT = 15.0


def _get(url: str, params: dict[str, str] | None = None) -> Any:
    resp = httpx.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def probe_greenhouse(source: ATSSource) -> list[dict[str, Any]]:
    """Fetch all open jobs from a Greenhouse board. Returns normalized list."""
    try:
        data = _get(source.base_url, params={"content": "true"})
    except Exception as exc:
        log.warning("Greenhouse probe failed for %s: %s", source.company, exc)
        return []
    jobs = []
    for j in data.get("jobs", []):
        location = (j.get("location") or {}).get("name", "")
        jobs.append({
            "company": source.company,
            "role": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "ats_source": "greenhouse",
            "location": location,
            "country": source.country,
            "sector": source.sector,
            "jd_text": _strip_html(j.get("content", "")),
        })
    return jobs


def probe_ashby(source: ATSSource) -> list[dict[str, Any]]:
    """Fetch open jobs from an Ashby board."""
    try:
        data = _get(source.base_url)
    except Exception as exc:
        log.warning("Ashby probe failed for %s: %s", source.company, exc)
        return []
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "company": source.company,
            "role": j.get("title", ""),
            "url": j.get("jobUrl", ""),
            "ats_source": "ashby",
            "location": j.get("locationName", ""),
            "country": source.country,
            "sector": source.sector,
            "jd_text": j.get("descriptionHtml", ""),
        })
    return jobs


def probe_lever(source: ATSSource) -> list[dict[str, Any]]:
    """Fetch open jobs from a Lever board."""
    try:
        data = _get(source.base_url, params={"mode": "json"})
    except Exception as exc:
        log.warning("Lever probe failed for %s: %s", source.company, exc)
        return []
    jobs = []
    for j in data:
        jobs.append({
            "company": source.company,
            "role": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "ats_source": "lever",
            "location": (j.get("categories") or {}).get("location", ""),
            "country": source.country,
            "sector": source.sector,
            "jd_text": (j.get("descriptionPlain") or ""),
        })
    return jobs


def probe(source: ATSSource) -> list[dict[str, Any]]:
    """Dispatch to the right ATS prober."""
    dispatch = {
        "greenhouse": probe_greenhouse,
        "ashby": probe_ashby,
        "lever": probe_lever,
    }
    fn = dispatch.get(source.name)
    if fn is None:
        log.warning("Unknown ATS source type: %s", source.name)
        return []
    return fn(source)


def _strip_html(html: str) -> str:
    """Very simple HTML tag stripper (no dependency on BeautifulSoup)."""
    import re
    return re.sub(r"<[^>]+>", " ", html).strip()
