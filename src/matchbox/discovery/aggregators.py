"""Aggregator job-source connectors — multi-company, query/region based.

Unlike the per-company ATS pollers in `pollers.py` (keyed on a company
slug), aggregators are keyed on a *query* (what/where) and/or a *region*.
Each function hits a documented public endpoint, parses the response, and
returns a list of `JobRecord` with the country-agnostic `country` and
`remote` fields populated. The runner can consume these the same way it
consumes ATS pollers; selection/scoring happen downstream.

Sources and their terms of service are verified in
`docs/product-thesis.md` ("Discovery architecture"). The ToS rules are
load-bearing and are enforced/annotated in code:

* **Adzuna** — free **BYO-key**; the caller supplies `app_id`/`app_key`
  (NEVER hardcode keys). Display "Jobs by Adzuna" attribution with a link
  back to the job (`JobRecord.url`) wherever Adzuna results are shown.
* **Himalayas** — public, no auth; terms explicitly permit powering search
  and AI agents. Honor attribution (link back) and back off on HTTP 429.
* **Remotive** — public, no auth; **<=4 calls/day**, attribution required,
  no re-publishing. Fine for a local single-user tool. Each `poll_remotive`
  call is one request, so the caller is responsible for the daily budget.

Endpoints are documented inline so the next person can re-verify them when
a vendor changes the contract.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from matchbox.core.text import strip_html
from matchbox.discovery.base import JobRecord

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
USER_AGENT = "Matchbox/0.4 (https://github.com/5h1vmani/matchbox)"

# Attribution strings the UI MUST surface alongside each source's results.
# Kept here so the wording lives next to the connector that owns the ToS.
ADZUNA_ATTRIBUTION = "Jobs by Adzuna"
HIMALAYAS_ATTRIBUTION = "Remote jobs by Himalayas"
REMOTIVE_ATTRIBUTION = "Remote jobs by Remotive"

# Words that, when present in a title/location/description, mark a role as
# remote. Matched case-insensitively against word-ish boundaries so we do
# not trip on substrings like "premotion".
_REMOTE_RE = re.compile(r"\b(remote|work\s*from\s*home|wfh|anywhere|distributed)\b", re.IGNORECASE)


class AggregatorError(Exception):
    """An aggregator connector failed in a way the runner should surface.

    Aggregators are query/region based, not company-slug based, so this is
    separate from `pollers.PollerError` (which carries an ats_type + slug).
    """

    def __init__(self, source: str, message: str) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source
        self.message = message


def _looks_remote(*fields: str | None) -> bool:
    """True if any field contains a remote signal (title/location/jd)."""
    return any(f and _REMOTE_RE.search(f) for f in fields)


def _get_json(
    client: httpx.Client,
    url: str,
    source: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET JSON with the shared timeout/UA and uniform error mapping.

    HTTP 429 is reported with its own message so a caller (or the runner)
    can recognise rate-limiting and back off, per the Himalayas/Remotive
    ToS. We do not retry here; the runner owns backoff.
    """
    try:
        r = client.get(
            url,
            params=params,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        raise AggregatorError(source, f"network error: {e}") from e
    if r.status_code == 429:
        raise AggregatorError(source, "rate limited (429) — back off and retry later")
    if r.status_code == 401 or r.status_code == 403:
        raise AggregatorError(source, f"auth rejected (HTTP {r.status_code}) — check API key")
    if r.status_code >= 400:
        raise AggregatorError(source, f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise AggregatorError(source, f"non-JSON response: {e}") from e


def _as_list(data: Any, key: str, source: str) -> list[dict[str, Any]]:
    """Pull `data[key]` and assert it is a list of objects, else raise."""
    if not isinstance(data, dict):
        raise AggregatorError(source, "unexpected response shape (expected object)")
    items = data.get(key)
    if items is None:
        # A well-formed response with zero results is valid, not an error.
        return []
    if not isinstance(items, list):
        raise AggregatorError(source, f"unexpected response shape ('{key}' is not a list)")
    return [item for item in items if isinstance(item, dict)]


# ─── Adzuna ───────────────────────────────────────────────────────────
# https://api.adzuna.com/v1/api/jobs/{country}/search/1
#   ?app_id=...&app_key=...&results_per_page=...&what=...&where=...
# Free BYO-key. Strongest verified India coverage (country="in", INR) plus
# EU/US/remote. ATTRIBUTION: any UI showing these results MUST display
# "Jobs by Adzuna" (ADZUNA_ATTRIBUTION) with a link back to JobRecord.url.
# Licence note (product-thesis): free/personal use is fine for a local OSS
# tool; commercial aggregation may need a licence — revisit on monetization.


_ADZUNA_CURRENCY = {
    "in": "INR",
    "gb": "GBP",
    "us": "USD",
    "au": "AUD",
    "ca": "CAD",
    "nz": "NZD",
    "sg": "SGD",
    "za": "ZAR",
    "pl": "PLN",
    "br": "BRL",
    "mx": "MXN",
    "de": "EUR",
    "fr": "EUR",
    "nl": "EUR",
    "at": "EUR",
    "it": "EUR",
    "es": "EUR",
}


def _adzuna_employment(job: dict[str, Any]) -> str | None:
    """Map Adzuna's contract_time/contract_type onto our employment_type."""
    ct = (job.get("contract_time") or "").lower()
    if ct in ("full_time", "part_time"):
        return ct
    cty = (job.get("contract_type") or "").lower()
    if cty == "contract":
        return "contract"
    if cty == "permanent":
        return "full_time"
    return None


def poll_adzuna(
    *,
    app_id: str,
    app_key: str,
    client: httpx.Client,
    country: str = "in",
    what: str = "",
    where: str = "",
    results_per_page: int = 50,
) -> list[JobRecord]:
    """Query Adzuna for one page of jobs in `country`.

    `app_id`/`app_key` are supplied by the caller (BYO key) — they are
    never stored or defaulted here. `country` is a lowercase Adzuna country
    code (e.g. "in", "gb", "us") and is recorded verbatim on each
    `JobRecord.country`. `remote` is inferred from the title/location/JD.
    """
    if not app_id or not app_key:
        raise AggregatorError("adzuna", "app_id and app_key are required (BYO key)")
    country = country.strip().lower()
    if not country:
        raise AggregatorError("adzuna", "country is required")

    # results_per_page only narrows what we ask for; only forward the
    # text filters when set so we do not send empty `what=`/`where=`.
    params: dict[str, Any] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results_per_page,
    }
    if what:
        params["what"] = what
    if where:
        params["where"] = where

    data = _get_json(
        client,
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
        "adzuna",
        params=params,
    )
    out: list[JobRecord] = []
    for job in _as_list(data, "results", "adzuna"):
        url = job.get("redirect_url") or ""
        if not url:
            # Without a link back we cannot honor the attribution rule, so
            # the row is useless — skip it rather than emit a dead record.
            continue
        location = job.get("location") or {}
        # Adzuna gives both a flat display_name and a hierarchical `area`
        # list (country -> region -> city). Prefer the display_name.
        loc_str = location.get("display_name")
        if not loc_str and isinstance(location.get("area"), list):
            loc_str = ", ".join(str(a) for a in location["area"] if a) or None
        title = (job.get("title") or "").strip()
        jd_text = strip_html(job.get("description"))
        company = (job.get("company") or {}).get("display_name") or "Unknown"
        out.append(
            JobRecord(
                ats_type="greenhouse",  # placeholder; runner overrides source typing
                source_slug=f"adzuna:{country}",
                company=company.strip() or "Unknown",
                title=title,
                location=loc_str,
                url=str(url),
                apply_url=str(url),
                jd_text=jd_text,
                posted_at=job.get("created"),
                country=country,
                remote=_looks_remote(title, loc_str, jd_text),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                salary_currency=_ADZUNA_CURRENCY.get(country),
                salary_period="year",
                employment_type=_adzuna_employment(job),
            )
        )
    return out


# ─── Himalayas ────────────────────────────────────────────────────────
# https://himalayas.app/jobs/api            (recent jobs)
# https://himalayas.app/jobs/api/search     (with ?query=...&limit=...)
# Public, no auth. Every job is remote. Terms explicitly permit powering
# search experiences and AI agents (best terms of the remote group) and
# expose an India filter via `locationRestrictions`. ATTRIBUTION: show
# HIMALAYAS_ATTRIBUTION with a link back. RATE LIMIT: HTTP 429 surfaces as
# an AggregatorError so the caller can back off (we do not hammer it).


def poll_himalayas(
    *,
    client: httpx.Client,
    query: str = "",
    limit: int = 50,
) -> list[JobRecord]:
    """Fetch remote jobs from Himalayas (optionally filtered by `query`).

    Uses the `/jobs/api/search` endpoint when a `query` is given, else the
    recent-jobs `/jobs/api` feed. Every result is `remote=True`. `country`
    is left None here: Himalayas reports allowed-location *restrictions*
    (a list, e.g. ["IN", "Worldwide"]), not a single hiring country, so a
    single `JobRecord.country` would be misleading — region filtering is
    left to the caller via the location text we preserve.
    """
    if query:
        url = "https://himalayas.app/jobs/api/search"
        params: dict[str, Any] = {"query": query, "limit": limit}
    else:
        url = "https://himalayas.app/jobs/api"
        params = {"limit": limit}

    data = _get_json(client, url, "himalayas", params=params)
    out: list[JobRecord] = []
    for job in _as_list(data, "jobs", "himalayas"):
        # The feed has used both `applicationLink` and `guidUrl`/`url` over
        # time; accept whichever is present.
        url_val = job.get("applicationLink") or job.get("guidUrl") or job.get("url") or ""
        if not url_val:
            continue
        # locationRestrictions is a list of region codes/names; join it for
        # the human-readable location and keep it for downstream filtering.
        restrictions = job.get("locationRestrictions")
        if isinstance(restrictions, list):
            loc_str = ", ".join(str(x) for x in restrictions if x) or None
        elif isinstance(restrictions, str):
            loc_str = restrictions or None
        else:
            loc_str = None
        out.append(
            JobRecord(
                ats_type="greenhouse",  # placeholder; runner overrides source typing
                source_slug="himalayas",
                company=(job.get("companyName") or job.get("company") or "Unknown").strip()
                or "Unknown",
                title=(job.get("title") or "").strip(),
                location=loc_str,
                url=str(url_val),
                apply_url=str(url_val),
                jd_text=strip_html(job.get("description") or job.get("excerpt")),
                posted_at=job.get("pubDate") or job.get("publishedDate") or job.get("pubDateUtc"),
                country=None,
                remote=True,
            )
        )
    return out


# ─── Remotive ─────────────────────────────────────────────────────────
# https://remotive.com/api/remote-jobs        (optionally ?search=&limit=)
# Public, no auth. Every job is remote. ToS: <=4 calls/day, attribution
# required (REMOTIVE_ATTRIBUTION + link back), no re-publishing. A local
# single-user tool stays well inside that. Each call here is ONE request;
# the caller owns the per-day budget (do not loop this connector).


def poll_remotive(
    *,
    client: httpx.Client,
    search: str = "",
    limit: int | None = None,
) -> list[JobRecord]:
    """Fetch remote jobs from Remotive.

    Optional `search` narrows results (Remotive's `search` param) and
    `limit` caps the count. Every result is `remote=True`. `country` is
    None: Remotive reports a free-text `candidate_required_location`
    (e.g. "Worldwide", "USA Only"), not a single hiring country, so it is
    preserved as the location string for the caller to filter on.
    """
    params: dict[str, Any] = {}
    if search:
        params["search"] = search
    if limit is not None:
        params["limit"] = limit

    data = _get_json(
        client,
        "https://remotive.com/api/remote-jobs",
        "remotive",
        params=params or None,
    )
    out: list[JobRecord] = []
    for job in _as_list(data, "jobs", "remotive"):
        url = job.get("url") or ""
        if not url:
            continue
        out.append(
            JobRecord(
                ats_type="greenhouse",  # placeholder; runner overrides source typing
                source_slug="remotive",
                company=(job.get("company_name") or "Unknown").strip() or "Unknown",
                title=(job.get("title") or "").strip(),
                location=job.get("candidate_required_location") or None,
                url=str(url),
                apply_url=str(url),
                jd_text=strip_html(job.get("description")),
                posted_at=job.get("publication_date"),
                country=None,
                remote=True,
            )
        )
    return out


# ─── dispatch ─────────────────────────────────────────────────────────
# SEPARATE from pollers.POLLERS: aggregators are query/region based, take
# keyword-only args (and BYO keys for Adzuna), and are not addressable by a
# company slug. The runner dispatches them on their own path.


AGGREGATORS = {
    "adzuna": poll_adzuna,
    "himalayas": poll_himalayas,
    "remotive": poll_remotive,
}
