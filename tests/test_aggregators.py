"""Tests for the aggregator connectors (Adzuna, Himalayas, Remotive).

Mirrors `test_discovery.py`: every request is served by an
`httpx.MockTransport`, so no network is touched. Fixture payloads mirror
each aggregator's documented response shape, including messy/missing
fields, empty result sets, and HTTP error paths (404, 429, 401).
"""

from __future__ import annotations

import httpx
import pytest

from matchbox.discovery import aggregators
from matchbox.discovery.aggregators import AGGREGATORS, AggregatorError


def _mock_client(
    responses: dict[str, dict | list | str | None],
    *,
    status_overrides: dict[str, int] | None = None,
) -> httpx.Client:
    """Serve `responses` keyed by URL path (query string stripped).

    A None value -> 404. `status_overrides` maps a path to a status code
    returned with an empty body (used for 429/401/403 error-path tests).
    """
    status_overrides = status_overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url in status_overrides:
            return httpx.Response(status_overrides[url], text="error")
        if url in responses:
            payload = responses[url]
            if payload is None:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=payload)
        return httpx.Response(500, text=f"unexpected URL: {url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"
HIMALAYAS_FEED = "https://himalayas.app/jobs/api"
HIMALAYAS_SEARCH = "https://himalayas.app/jobs/api/search"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


# ─── Adzuna ───────────────────────────────────────────────────────────


def test_adzuna_parse_and_country_tag() -> None:
    client = _mock_client(
        {
            ADZUNA_URL: {
                "count": 1,
                "results": [
                    {
                        "title": "Backend Engineer",
                        "redirect_url": "https://adzuna.example/jobs/1",
                        "description": "<p>Build <b>APIs</b> in Python.</p>",
                        "location": {
                            "display_name": "Bengaluru, Karnataka",
                            "area": ["India", "Karnataka", "Bengaluru"],
                        },
                        "company": {"display_name": "Acme Corp"},
                        "created": "2026-05-20T00:00:00Z",
                    }
                ],
            }
        }
    )
    rows = aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Backend Engineer"
    assert row.company == "Acme Corp"
    assert row.url == "https://adzuna.example/jobs/1"
    assert row.apply_url == "https://adzuna.example/jobs/1"
    assert row.jd_text == "Build APIs in Python."
    assert "<" not in row.jd_text
    assert row.location == "Bengaluru, Karnataka"
    assert row.country == "in"  # taken verbatim from the query country
    assert row.posted_at == "2026-05-20T00:00:00Z"
    assert row.remote is False  # nothing remote in title/location/jd


def test_adzuna_remote_detected_from_text() -> None:
    client = _mock_client(
        {
            ADZUNA_URL: {
                "results": [
                    {
                        "title": "Senior Engineer (Remote)",
                        "redirect_url": "https://adzuna.example/jobs/2",
                        "description": "Fully distributed team.",
                        "location": {"display_name": "Anywhere in India"},
                        "company": {"display_name": "RemoteCo"},
                    }
                ]
            }
        }
    )
    rows = aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert rows[0].remote is True


def test_adzuna_country_is_lowercased_and_used_in_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    aggregators.poll_adzuna(app_id="id", app_key="k", client=client, country="GB")
    assert seen["path"] == "/v1/api/jobs/gb/search/1"
    # BYO key flows through as query params; never hardcoded.
    assert "app_id=id" in seen["query"]
    assert "app_key=k" in seen["query"]


def test_adzuna_only_sends_what_where_when_set() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # No what/where -> those params must be absent.
    aggregators.poll_adzuna(app_id="id", app_key="k", client=client, country="in")
    assert "what=" not in captured["query"]
    assert "where=" not in captured["query"]
    # With them set -> present.
    aggregators.poll_adzuna(
        app_id="id", app_key="k", client=client, country="in", what="python", where="remote"
    )
    assert "what=python" in captured["query"]
    assert "where=remote" in captured["query"]


def test_adzuna_missing_optional_fields_are_graceful() -> None:
    client = _mock_client(
        {
            ADZUNA_URL: {
                "results": [
                    # No company, no location, no description, no created.
                    {"title": "Bare Job", "redirect_url": "https://adzuna.example/jobs/3"}
                ]
            }
        }
    )
    rows = aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert len(rows) == 1
    assert rows[0].company == "Unknown"
    assert rows[0].location is None
    assert rows[0].jd_text == ""
    assert rows[0].posted_at is None
    assert rows[0].remote is False


def test_adzuna_skips_results_without_redirect_url() -> None:
    client = _mock_client(
        {
            ADZUNA_URL: {
                "results": [
                    {"title": "No link", "description": "x"},
                    {"title": "Has link", "redirect_url": "https://adzuna.example/jobs/4"},
                ]
            }
        }
    )
    rows = aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert len(rows) == 1
    assert rows[0].title == "Has link"


def test_adzuna_empty_results_is_not_an_error() -> None:
    client = _mock_client({ADZUNA_URL: {"count": 0, "results": []}})
    rows = aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert rows == []


def test_adzuna_requires_byo_key() -> None:
    client = _mock_client({ADZUNA_URL: {"results": []}})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_adzuna(app_id="", app_key="key", client=client)
    assert "app_id" in str(exc.value)
    with pytest.raises(AggregatorError):
        aggregators.poll_adzuna(app_id="id", app_key="", client=client)


def test_adzuna_auth_rejected_surfaces_clearly() -> None:
    client = _mock_client({}, status_overrides={ADZUNA_URL: 401})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_adzuna(app_id="bad", app_key="bad", client=client, country="in")
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


def test_adzuna_unexpected_shape_raises() -> None:
    client = _mock_client({ADZUNA_URL: {"results": "not-a-list"}})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_adzuna(app_id="id", app_key="key", client=client, country="in")
    assert "shape" in str(exc.value)


# ─── Himalayas ────────────────────────────────────────────────────────


def test_himalayas_parse_all_remote() -> None:
    client = _mock_client(
        {
            HIMALAYAS_FEED: {
                "total": 1,
                "jobs": [
                    {
                        "title": "Platform Engineer",
                        "companyName": "Globex",
                        "applicationLink": "https://himalayas.example/jobs/1",
                        "locationRestrictions": ["IN", "Worldwide"],
                        "description": "<div>Run <i>k8s</i> clusters.</div>",
                        "pubDate": "2026-05-18",
                    }
                ],
            }
        }
    )
    rows = aggregators.poll_himalayas(client=client)
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Platform Engineer"
    assert row.company == "Globex"
    assert row.url == "https://himalayas.example/jobs/1"
    assert row.jd_text == "Run k8s clusters."
    assert row.location == "IN, Worldwide"
    assert row.remote is True  # every Himalayas job is remote
    assert row.country is None  # restrictions are a list, not a single country
    assert row.posted_at == "2026-05-18"


def test_himalayas_uses_search_endpoint_when_query_given() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    aggregators.poll_himalayas(client=client, query="python", limit=10)
    assert seen["path"] == "/jobs/api/search"
    assert "query=python" in seen["query"]
    assert "limit=10" in seen["query"]


def test_himalayas_feed_endpoint_when_no_query() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    aggregators.poll_himalayas(client=client)
    assert seen["path"] == "/jobs/api"


def test_himalayas_field_name_variants_and_string_restriction() -> None:
    client = _mock_client(
        {
            HIMALAYAS_FEED: {
                "jobs": [
                    {
                        # alternate field names: company/guidUrl/excerpt/publishedDate
                        "title": "SRE",
                        "company": "Initech",
                        "guidUrl": "https://himalayas.example/jobs/2",
                        "locationRestrictions": "Worldwide",
                        "excerpt": "On-call rotation.",
                        "publishedDate": "2026-05-10",
                    }
                ]
            }
        }
    )
    rows = aggregators.poll_himalayas(client=client)
    assert rows[0].company == "Initech"
    assert rows[0].url == "https://himalayas.example/jobs/2"
    assert rows[0].location == "Worldwide"
    assert rows[0].jd_text == "On-call rotation."
    assert rows[0].posted_at == "2026-05-10"


def test_himalayas_missing_fields_graceful() -> None:
    client = _mock_client(
        {
            HIMALAYAS_FEED: {
                "jobs": [{"title": "Bare", "applicationLink": "https://himalayas.example/jobs/3"}]
            }
        }
    )
    rows = aggregators.poll_himalayas(client=client)
    assert rows[0].company == "Unknown"
    assert rows[0].location is None
    assert rows[0].jd_text == ""
    assert rows[0].posted_at is None
    assert rows[0].remote is True


def test_himalayas_skips_jobs_without_url() -> None:
    client = _mock_client(
        {
            HIMALAYAS_FEED: {
                "jobs": [
                    {"title": "No link", "companyName": "X"},
                    {"title": "Link", "url": "https://himalayas.example/jobs/4"},
                ]
            }
        }
    )
    rows = aggregators.poll_himalayas(client=client)
    assert len(rows) == 1
    assert rows[0].title == "Link"


def test_himalayas_empty_and_missing_jobs_key() -> None:
    assert aggregators.poll_himalayas(client=_mock_client({HIMALAYAS_FEED: {"jobs": []}})) == []
    # A response object without the "jobs" key -> treated as zero results.
    assert aggregators.poll_himalayas(client=_mock_client({HIMALAYAS_FEED: {"total": 0}})) == []


def test_himalayas_rate_limit_429_surfaces() -> None:
    client = _mock_client({}, status_overrides={HIMALAYAS_FEED: 429})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_himalayas(client=client)
    assert "429" in str(exc.value)
    assert "rate lim" in str(exc.value).lower()


def test_himalayas_bad_shape_raises() -> None:
    client = _mock_client({HIMALAYAS_FEED: ["not", "an", "object"]})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_himalayas(client=client)
    assert "shape" in str(exc.value)


# ─── Remotive ─────────────────────────────────────────────────────────


def test_remotive_parse_all_remote() -> None:
    client = _mock_client(
        {
            REMOTIVE_URL: {
                "job-count": 1,
                "jobs": [
                    {
                        "title": "Data Engineer",
                        "company_name": "Hooli",
                        "url": "https://remotive.example/jobs/1",
                        "candidate_required_location": "Worldwide",
                        "description": "<p>Build <b>ETL</b> with Spark</p>",
                        "publication_date": "2026-05-15T12:00:00",
                        "job_type": "full_time",
                    }
                ],
            }
        }
    )
    rows = aggregators.poll_remotive(client=client)
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Data Engineer"
    assert row.company == "Hooli"
    assert row.url == "https://remotive.example/jobs/1"
    assert row.jd_text == "Build ETL with Spark"
    assert "<" not in row.jd_text
    assert row.location == "Worldwide"
    assert row.remote is True  # every Remotive job is remote
    assert row.country is None
    assert row.posted_at == "2026-05-15T12:00:00"


def test_remotive_search_and_limit_params_forwarded() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    aggregators.poll_remotive(client=client, search="python", limit=5)
    assert "search=python" in seen["query"]
    assert "limit=5" in seen["query"]


def test_remotive_no_params_sends_clean_request() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"jobs": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    aggregators.poll_remotive(client=client)
    assert seen["query"] == ""  # no empty search=/limit= appended


def test_remotive_missing_fields_graceful() -> None:
    client = _mock_client(
        {REMOTIVE_URL: {"jobs": [{"title": "Bare", "url": "https://remotive.example/jobs/2"}]}}
    )
    rows = aggregators.poll_remotive(client=client)
    assert rows[0].company == "Unknown"
    assert rows[0].location is None
    assert rows[0].jd_text == ""
    assert rows[0].posted_at is None
    assert rows[0].remote is True


def test_remotive_skips_jobs_without_url() -> None:
    client = _mock_client(
        {
            REMOTIVE_URL: {
                "jobs": [
                    {"title": "No link", "company_name": "X"},
                    {"title": "Link", "url": "https://remotive.example/jobs/3"},
                ]
            }
        }
    )
    rows = aggregators.poll_remotive(client=client)
    assert len(rows) == 1
    assert rows[0].title == "Link"


def test_remotive_empty_results() -> None:
    client = _mock_client({REMOTIVE_URL: {"job-count": 0, "jobs": []}})
    assert aggregators.poll_remotive(client=client) == []


def test_remotive_404_surfaces() -> None:
    client = _mock_client({REMOTIVE_URL: None})
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_remotive(client=client)
    assert "404" in str(exc.value)


def test_remotive_non_json_surfaces() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_remotive(client=client)
    assert "non-JSON" in str(exc.value)


# ─── network errors + registry ────────────────────────────────────────


def test_network_error_surfaces_as_aggregator_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AggregatorError) as exc:
        aggregators.poll_remotive(client=client)
    assert "network error" in str(exc.value)


def test_aggregators_registry_is_separate_and_complete() -> None:
    """The aggregator registry is distinct from the ATS POLLERS and maps
    every connector name to its callable."""
    from matchbox.discovery import pollers

    assert set(AGGREGATORS) == {"adzuna", "himalayas", "remotive"}
    assert AGGREGATORS["adzuna"] is aggregators.poll_adzuna
    assert AGGREGATORS["himalayas"] is aggregators.poll_himalayas
    assert AGGREGATORS["remotive"] is aggregators.poll_remotive
    # No overlap with the company-slug ATS pollers.
    assert set(AGGREGATORS).isdisjoint(set(pollers.POLLERS))


def test_attribution_strings_present() -> None:
    """ToS attribution wording must be defined for every aggregator."""
    assert "Adzuna" in aggregators.ADZUNA_ATTRIBUTION
    assert "Himalayas" in aggregators.HIMALAYAS_ATTRIBUTION
    assert "Remotive" in aggregators.REMOTIVE_ATTRIBUTION
