"""Aggregator discovery over the JSON sources API (the React replacement)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.web.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    with TestClient(create_app()) as c:
        yield c


def test_scan_remote_returns_per_aggregator_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from matchbox.discovery.runner import AggregatorResult
    from matchbox.web.routes import sources_api

    monkeypatch.setattr(
        sources_api,
        "scan_aggregators",
        lambda conn, **kw: [
            AggregatorResult("himalayas", True, 3, 3, None),
            AggregatorResult("remotive", True, 2, 2, None),
        ],
    )
    body = client.post("/api/sources/scan-remote").json()
    assert {r["name"] for r in body["results"]} == {"himalayas", "remotive"}
    assert sum(r["inserted"] for r in body["results"]) == 5


def test_save_and_read_adzuna(client: TestClient) -> None:
    r = client.post(
        "/api/sources/adzuna",
        json={"app_id": "myid", "app_key": "mykey", "country": "in", "what": "backend"},
    )
    assert r.status_code == 200 and r.json()["ok"] == "true"
    # The saved config is read back via the sources view-model.
    adzuna = client.get("/api/sources").json()["adzuna"]
    assert adzuna["app_id"] == "myid"
    assert adzuna["queries"][0]["what"] == "backend"
