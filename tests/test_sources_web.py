"""End-to-end tests for the /sources routes.

The actual HTTP calls to ATS APIs are mocked via httpx.MockTransport
through monkeypatching httpx.Client in the runner.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # type: ignore[no-untyped-def]
    """Patch httpx.Client so any code under test gets a MockTransport."""
    import httpx as _httpx

    real_client = _httpx.Client

    def fake_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = _httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(_httpx, "Client", fake_client)


def test_sources_index_renders(client: TestClient) -> None:
    r = client.get("/sources")
    assert r.status_code == 200
    assert "Sources" in r.text
    assert "Add a company" in r.text


def test_add_source_creates_row(client: TestClient) -> None:
    r = client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "anthropic", "company": "Anthropic"},
    )
    assert r.status_code == 200
    assert "Anthropic" in r.text
    assert "anthropic" in r.text


def test_add_source_rejects_duplicate(client: TestClient) -> None:
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "anthropic", "company": "Anthropic"},
    )
    r = client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "anthropic", "company": "Anthropic"},
    )
    assert r.status_code == 409


def test_add_source_rejects_unsupported_ats(client: TestClient) -> None:
    r = client.post(
        "/sources",
        data={"ats_type": "myspace", "slug": "x", "company": "Y"},
    )
    assert r.status_code == 400


def test_scan_one_inserts_jobs(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "anthropic", "company": "Anthropic"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "FDE",
                        "absolute_url": "https://job.example/x",
                        "content": "JD body",
                        "location": {"name": "Remote"},
                    }
                ]
            },
        )

    _patch_httpx(monkeypatch, handler)

    sources_page = client.get("/sources").text
    source_id = int(re.search(r'source-(\d+)"', sources_page).group(1))  # type: ignore[union-attr]

    r = client.post(f"/sources/{source_id}/scan")
    assert r.status_code == 200
    assert "ok" in r.text
    # the row now reflects job_count = 1
    assert ">1<" in r.text or "1\n" in r.text or "1 " in r.text


def test_scan_one_records_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "bogus", "company": "Bogus"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch_httpx(monkeypatch, handler)

    sources_page = client.get("/sources").text
    source_id = int(re.search(r'source-(\d+)"', sources_page).group(1))  # type: ignore[union-attr]

    r = client.post(f"/sources/{source_id}/scan")
    assert r.status_code == 200
    assert "error" in r.text.lower()
    assert "404" in r.text


def test_scan_all_summary(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "good", "company": "Good"},
    )
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "bad", "company": "Bad"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if "/good/" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "title": "T",
                            "absolute_url": "https://job.example/g",
                            "content": "JD",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    _patch_httpx(monkeypatch, handler)

    r = client.post("/sources/scan-all")
    assert r.status_code == 200
    assert "1 ok" in r.text
    assert "1 failed" in r.text
    assert "1 new job" in r.text


def test_toggle_and_delete(client: TestClient) -> None:
    client.post(
        "/sources",
        data={"ats_type": "greenhouse", "slug": "x", "company": "X"},
    )
    page = client.get("/sources").text
    source_id = int(re.search(r'source-(\d+)"', page).group(1))  # type: ignore[union-attr]

    r1 = client.post(f"/sources/{source_id}/toggle")
    assert r1.status_code == 200
    assert "enable" in r1.text  # since it's now disabled, the button reads "enable"

    r2 = client.delete(f"/sources/{source_id}")
    assert r2.status_code == 200
    assert f"source-{source_id}" not in client.get("/sources").text


def test_probe_route_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": [{"title": "T", "absolute_url": "https://x.example/1", "content": "c"}]},
        )

    _patch_httpx(monkeypatch, handler)
    r = client.post(
        "/sources/probe",
        data={"ats_type": "greenhouse", "slug": "x", "company": "X"},
    )
    assert r.status_code == 200
    assert "probe ok" in r.text


def test_probe_route_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch_httpx(monkeypatch, handler)
    r = client.post(
        "/sources/probe",
        data={"ats_type": "greenhouse", "slug": "bogus", "company": ""},
    )
    assert r.status_code == 200
    assert "probe failed" in r.text
    assert "404" in r.text
