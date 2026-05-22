"""ATS pollers — one function per supported board.

Each poller takes a slug + an `httpx.Client`, hits the documented public
endpoint, parses the response, and returns a list of `JobRecord`. The
runner wraps these with retries, backoff, and DB upsert.

Endpoints are public JSON APIs the v0.2 audit identified or that the
section 10 of the design adds; URLs are documented inline for the next
person to verify when a vendor changes them.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

import httpx

from matchbox.discovery.base import AtsType, JobRecord, PollerError

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
USER_AGENT = "Matchbox/0.3 (https://github.com/5h1vmani/matchbox)"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(html))).strip()


def _get_json(client: httpx.Client, url: str, ats_type: AtsType, slug: str) -> Any:
    try:
        r = client.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except httpx.RequestError as e:
        raise PollerError(ats_type, slug, f"network error: {e}") from e
    if r.status_code == 404:
        raise PollerError(ats_type, slug, "board not found (404)")
    if r.status_code >= 400:
        raise PollerError(ats_type, slug, f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise PollerError(ats_type, slug, f"non-JSON response: {e}") from e


# ─── Greenhouse ───────────────────────────────────────────────────────
# https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
# Public, no auth. Single page response.


def poll_greenhouse(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    data = _get_json(
        client,
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "greenhouse",
        slug,
    )
    if not isinstance(data, dict) or "jobs" not in data:
        raise PollerError("greenhouse", slug, "unexpected response shape")
    out: list[JobRecord] = []
    for job in data["jobs"]:
        url = job.get("absolute_url") or ""
        if not url:
            continue
        out.append(
            JobRecord(
                ats_type="greenhouse",
                source_slug=slug,
                company=company,
                title=job.get("title", "").strip(),
                location=(job.get("location") or {}).get("name"),
                url=url,
                apply_url=url,
                jd_text=_strip_html(job.get("content", "")),
                posted_at=job.get("updated_at"),
            )
        )
    return out


# ─── Lever ────────────────────────────────────────────────────────────
# https://api.lever.co/v0/postings/{slug}?mode=json
# Public, no auth. Single page response (array at top level).


def poll_lever(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    data = _get_json(
        client,
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "lever",
        slug,
    )
    if not isinstance(data, list):
        raise PollerError("lever", slug, "unexpected response shape (expected array)")
    out: list[JobRecord] = []
    for job in data:
        url = job.get("hostedUrl") or ""
        if not url:
            continue
        out.append(
            JobRecord(
                ats_type="lever",
                source_slug=slug,
                company=company,
                title=job.get("text", "").strip(),
                location=(job.get("categories") or {}).get("location"),
                url=url,
                apply_url=job.get("applyUrl") or url,
                jd_text=(job.get("descriptionPlain") or _strip_html(job.get("description"))),
                posted_at=str(job["createdAt"]) if "createdAt" in job else None,
            )
        )
    return out


# ─── Ashby ────────────────────────────────────────────────────────────
# https://api.ashbyhq.com/posting-api/job-board/{slug}
# Public, no auth. Single response with `jobs` array.


def poll_ashby(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    data = _get_json(
        client,
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "ashby",
        slug,
    )
    if not isinstance(data, dict) or "jobs" not in data:
        raise PollerError("ashby", slug, "unexpected response shape")
    out: list[JobRecord] = []
    for job in data["jobs"]:
        url = job.get("jobUrl") or ""
        if not url:
            continue
        out.append(
            JobRecord(
                ats_type="ashby",
                source_slug=slug,
                company=company,
                title=job.get("title", "").strip(),
                location=job.get("locationName"),
                url=url,
                apply_url=job.get("applyUrl") or url,
                jd_text=_strip_html(job.get("descriptionHtml", "")),
                posted_at=job.get("publishedAt"),
            )
        )
    return out


# ─── Workable ─────────────────────────────────────────────────────────
# https://apply.workable.com/api/v3/accounts/{slug}/jobs
# Public widget endpoint. POST form; we use GET (returns same data).
# Note: the modern `apply.workable.com` API is the recommended one;
# older `{slug}.workable.com/spi/v3/jobs` still works but deprecated.


def poll_workable(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    data = _get_json(
        client,
        f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
        "workable",
        slug,
    )
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise PollerError("workable", slug, "unexpected response shape (no results array)")
    out: list[JobRecord] = []
    for job in results:
        url = job.get("url") or job.get("shortlink") or ""
        if not url:
            continue
        location = job.get("location") or {}
        loc_str = ", ".join(x for x in (location.get("city"), location.get("country")) if x) or None
        out.append(
            JobRecord(
                ats_type="workable",
                source_slug=slug,
                company=company,
                title=job.get("title", "").strip(),
                location=loc_str,
                url=url,
                apply_url=url,
                jd_text=_strip_html(job.get("description") or job.get("full_description") or ""),
                posted_at=job.get("published_on"),
            )
        )
    return out


# ─── SmartRecruiters ──────────────────────────────────────────────────
# https://api.smartrecruiters.com/v1/companies/{slug}/postings
# Public, no auth. Paginated with `offset`/`limit`; we ask for limit=100.


def poll_smartrecruiters(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    out: list[JobRecord] = []
    offset = 0
    limit = 100
    while True:
        url = (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?limit={limit}&offset={offset}"
        )
        data = _get_json(client, url, "smartrecruiters", slug)
        if not isinstance(data, dict):
            raise PollerError("smartrecruiters", slug, "unexpected response shape")
        content = data.get("content") or []
        for job in content:
            posting_url = job.get("ref") or job.get("postingUrl")
            apply_url = job.get("applyUrl") or posting_url
            if not posting_url:
                continue
            loc = job.get("location") or {}
            loc_str = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x) or None
            # JD text isn't in the listing endpoint; the runner can fetch the
            # detail if/when we need it. For v1, listing-only is acceptable.
            out.append(
                JobRecord(
                    ats_type="smartrecruiters",
                    source_slug=slug,
                    company=company,
                    title=(job.get("name") or "").strip(),
                    location=loc_str,
                    url=str(posting_url),
                    apply_url=str(apply_url) if apply_url else None,
                    jd_text=_strip_html(
                        job.get("jobAd", {})
                        .get("sections", {})
                        .get("jobDescription", {})
                        .get("text", "")
                    ),
                    posted_at=job.get("releasedDate") or job.get("createdOn"),
                )
            )
        total = data.get("totalFound", len(content))
        offset += len(content)
        if len(content) < limit or offset >= total:
            break
    return out


# ─── Recruitee ────────────────────────────────────────────────────────
# https://{slug}.recruitee.com/api/offers/
# Public, no auth, single response.


def poll_recruitee(slug: str, company: str, client: httpx.Client) -> list[JobRecord]:
    data = _get_json(
        client,
        f"https://{slug}.recruitee.com/api/offers/",
        "recruitee",
        slug,
    )
    offers = data.get("offers") if isinstance(data, dict) else None
    if not isinstance(offers, list):
        raise PollerError("recruitee", slug, "unexpected response shape (no offers array)")
    out: list[JobRecord] = []
    for job in offers:
        url = job.get("careers_apply_url") or job.get("careers_url") or ""
        if not url:
            continue
        loc = ", ".join(x for x in (job.get("city"), job.get("country")) if x) or None
        out.append(
            JobRecord(
                ats_type="recruitee",
                source_slug=slug,
                company=company,
                title=(job.get("title") or "").strip(),
                location=loc,
                url=url,
                apply_url=job.get("careers_apply_url") or url,
                jd_text=_strip_html(job.get("description") or ""),
                posted_at=job.get("published_at"),
            )
        )
    return out


# ─── dispatch ─────────────────────────────────────────────────────────


POLLERS = {
    "greenhouse": poll_greenhouse,
    "lever": poll_lever,
    "ashby": poll_ashby,
    "workable": poll_workable,
    "smartrecruiters": poll_smartrecruiters,
    "recruitee": poll_recruitee,
}
