"""Brain web route tests: the BYOK gates and the SSE framing.

No real network. The runner is monkeypatched to a stub that just emits two
progress steps and returns a result, so these test the route's contract -- the
409-without-key and 400-without-confirm gates (mirroring ai.py), and that the
streamed body carries the step frames followed by a final `done` event -- not the
runner's behaviour (that is test_brain_runner.py).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from matchbox.core import secrets
from matchbox.web.app import create_app
from matchbox.web.routes import brain


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def _set_key() -> None:
    secrets.write_key("sk-test-123")


# ── gates ────────────────────────────────────────────────────────────────────


def test_tailor_409_without_key(client: TestClient) -> None:
    r = client.post("/api/brain/tailor", json={"job_id": 1, "confirm": True})
    assert r.status_code == 409
    assert r.json()["detail"] == "no API key configured"


def test_ingest_409_without_key(client: TestClient) -> None:
    r = client.post("/api/brain/ingest", json={"confirm": True})
    assert r.status_code == 409


def test_tailor_400_without_confirm(client: TestClient) -> None:
    _set_key()
    r = client.post("/api/brain/tailor", json={"job_id": 1, "confirm": False})
    assert r.status_code == 400
    assert r.json()["detail"] == "confirm required"


def test_ingest_400_without_confirm(client: TestClient) -> None:
    _set_key()
    r = client.post("/api/brain/ingest", json={"confirm": False})
    assert r.status_code == 400


# ── happy-path SSE ───────────────────────────────────────────────────────────


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """Pull the JSON objects out of a `data: {...}` SSE stream."""
    out: list[dict[str, Any]] = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def test_tailor_streams_steps_then_done(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_key()

    def stub_run_tailor(
        conn: Any, profile: str, job_id: int, complete: Any, progress: Any, **kw: Any
    ) -> dict[str, Any]:
        progress("requirements", "extracting JD requirements")
        progress("assemble", "rendering the CV")
        return {"run_id": "2026-06-11-001", "cv_path": "runs/x/cv.pdf", "gaps": []}

    # Avoid building a real provider client (no network): stub the completer too.
    monkeypatch.setattr(brain, "byok_completer", lambda conn, profile: lambda s, u: "{}")
    monkeypatch.setattr(brain, "run_tailor", stub_run_tailor)

    r = client.post("/api/brain/tailor", json={"job_id": 7, "confirm": True})
    assert r.status_code == 200
    events = _parse_sse(r.text)

    steps = [e for e in events if "step" in e]
    assert [e["step"] for e in steps] == ["requirements", "assemble"]

    final = events[-1]
    assert final["done"] is True
    assert final["run_id"] == "2026-06-11-001"


def test_ingest_streams_steps_then_done(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_key()

    def stub_run_ingest(
        conn: Any, profile: str, complete: Any, progress: Any, **kw: Any
    ) -> dict[str, int]:
        progress("read", "reading staged files")
        progress("save", "writing rows")
        return {"bullets": 3, "experiences": 1}

    monkeypatch.setattr(brain, "byok_completer", lambda conn, profile: lambda s, u: "{}")
    monkeypatch.setattr(brain, "run_ingest", stub_run_ingest)

    r = client.post("/api/brain/ingest", json={"confirm": True})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    assert [e["step"] for e in events if "step" in e] == ["read", "save"]
    assert events[-1]["done"] is True
    assert events[-1]["bullets"] == 3


def test_tailor_surfaces_runner_error_as_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_key()

    def boom(
        conn: Any, profile: str, job_id: int, complete: Any, progress: Any, **kw: Any
    ) -> dict[str, Any]:
        from matchbox.brain.llm import BrainError

        raise BrainError("job 7 not found")

    monkeypatch.setattr(brain, "byok_completer", lambda conn, profile: lambda s, u: "{}")
    monkeypatch.setattr(brain, "run_tailor", boom)

    r = client.post("/api/brain/tailor", json={"job_id": 7, "confirm": True})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    assert events[-1]["error"] == "job 7 not found"
