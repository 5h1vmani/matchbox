"""Web wiring for aggregator discovery: scan-remote, Adzuna config, filters."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_scan_remote_button(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from matchbox.discovery.runner import AggregatorResult
    from matchbox.web.routes import sources as sources_mod

    monkeypatch.setattr(
        sources_mod,
        "scan_aggregators",
        lambda conn, **kw: [
            AggregatorResult("himalayas", True, 3, 3, None),
            AggregatorResult("remotive", True, 2, 2, None),
        ],
    )
    r = client.post("/sources/scan-remote")
    assert r.status_code == 200
    assert "added 5" in r.text


def test_save_and_prefill_adzuna(client: TestClient) -> None:
    r = client.post(
        "/sources/adzuna",
        data={"app_id": "myid", "app_key": "mykey", "country": "in", "what": "backend"},
    )
    assert r.status_code == 200
    assert "saved" in r.text.lower()
    page = client.get("/sources").text
    assert 'value="myid"' in page  # the saved key prefilled into the form


def test_inbox_remote_and_country_filters(client: TestClient) -> None:
    client.get("/sources")  # trigger lazy migrate
    from matchbox.core.db import connect

    conn = connect()
    conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status, remote, country) "
        "VALUES ('R', 'Remote Eng', 'https://x/r', 'jd', 'new', 1, NULL)"
    )
    conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status, remote, country) "
        "VALUES ('O', 'Onsite Eng', 'https://x/o', 'jd', 'new', 0, 'in')"
    )
    conn.close()

    remote_page = client.get("/inbox?remote=true").text
    assert "Remote Eng" in remote_page
    assert "Onsite Eng" not in remote_page

    country_page = client.get("/inbox?country=in").text
    assert "Onsite Eng" in country_page
    assert "Remote Eng" not in country_page
