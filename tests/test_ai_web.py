"""BYOK AI layer: voice-check (form only), library facts, the per-profile secret
store, AI config, and the streaming proxy's normalization + degradation."""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matchbox.core import library as lib
from matchbox.core import secrets
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.web.app import create_app
from matchbox.web.routes import ai


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MATCHBOX_DB", str(tmp_path / "matchbox.db"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed_conn() -> sqlite3.Connection:
    conn = connect(Path(os.environ["MATCHBOX_DB"]))
    migrate(conn)
    return conn


# ── voice-check: form only ───────────────────────────────────────────────────────


def test_voice_check_passes_clean_prose_and_flags_banned_word(client: TestClient) -> None:
    clean = (
        "I led the payments rewrite at Acme, cutting checkout latency and shipping the new "
        "ledger to production over two quarters. I would bring that same focus on reliability "
        "and measured delivery to your platform team, and I am ready to start soon."
    )
    r = client.post("/api/voice-check", json={"text": clean, "scope": "cover"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    bad = clean + " I love to leverage synergy."
    r = client.post("/api/voice-check", json={"text": bad, "scope": "cover"})
    body = r.json()
    assert body["ok"] is False
    rules = {v["rule"] for v in body["violations"]}
    assert "banned_word" in rules


def test_voice_check_word_count_is_scope_specific(client: TestClient) -> None:
    text = "Led the migration of our billing system to a new ledger."  # 11 words
    # The CV-bullet tier accepts 8-25 words; the cover tier requires 40+.
    assert (
        client.post("/api/voice-check", json={"text": text, "scope": "cover"}).json()["ok"] is False
    )
    assert (
        client.post("/api/voice-check", json={"text": text, "scope": "cv_bullet"}).json()["ok"]
        is True
    )


# ── library facts: verified grounding ────────────────────────────────────────────


def test_library_facts_returns_only_verified_by_default(client: TestClient) -> None:
    conn = _seed_conn()
    try:
        exp = lib.add_experience(conn, company="Acme", role="Engineer")
        lib.add_bullet(conn, experience_id=exp.id, text="Shipped the ledger.", facts_verified=True)
        lib.add_bullet(conn, experience_id=exp.id, text="Unverified claim.", facts_verified=False)
        lib.add_skill(conn, name="Python", category="Languages")
    finally:
        conn.close()

    facts = client.get("/api/library/facts").json()
    assert facts["verified_only"] is True
    texts = [b["text"] for e in facts["experiences"] for b in e["bullets"]]
    assert "Shipped the ledger." in texts
    assert "Unverified claim." not in texts  # the honesty lever
    assert {"name": "Python", "category": "Languages"} in facts["skills"]

    # verified=0 surfaces the full library (review surfaces only).
    all_facts = client.get("/api/library/facts?verified=0").json()
    all_texts = [b["text"] for e in all_facts["experiences"] for b in e["bullets"]]
    assert "Unverified claim." in all_texts


# ── secret store: 0600, write-only over the wire ─────────────────────────────────


def test_secret_store_roundtrip_and_perms(client: TestClient) -> None:
    # No key initially.
    assert client.get("/api/ai/config").json()["hasKey"] is False

    r = client.post("/api/ai/key", json={"key": "sk-test-123"})
    assert r.json()["hasKey"] is True

    key_file = Path(os.environ["MATCHBOX_DB"]).parent / secrets.KEY_FILENAME
    assert key_file.exists()
    # 0600 -- owner read/write only.
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    # The key is on disk but never returned to the browser.
    assert "sk-test-123" not in r.text
    assert secrets.read_key() == "sk-test-123"

    assert client.delete("/api/ai/key").json()["hasKey"] is False
    assert not key_file.exists()


def test_ai_config_provider_validation_and_persist(client: TestClient) -> None:
    r = client.post("/api/ai/config", json={"provider": "openai", "model": "gpt-4o-mini"})
    body = r.json()
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o-mini"
    assert client.post("/api/ai/config", json={"provider": "bogus"}).status_code == 400


# ── streaming proxy: honest degradation + normalization ──────────────────────────


def test_ai_stream_409_without_key(client: TestClient) -> None:
    # No key -> 409 so the browser falls back to its demo stream.
    r = client.post("/api/ai/stream", json={"prompt": "Write a cover paragraph."})
    assert r.status_code == 409


class _FakeStream:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def aiter_lines(self) -> AsyncIterator[str]:
        for ln in self._lines:
            yield ln

    async def aread(self) -> bytes:
        return b"error body"


class _FakeClient:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self._sc = status_code
        self._lines = lines

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def stream(self, *a: object, **k: object) -> _FakeStream:
        return _FakeStream(self._sc, self._lines)


async def test_relay_normalizes_anthropic_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello "}}',
        "event: ping",
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "world"}}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: _FakeClient(200, lines))
    out = b"".join(
        [chunk async for chunk in ai._relay("anthropic", "m", "k", "", "prompt", 100)]
    ).decode()
    assert '{"text": "Hello "}' in out
    assert '{"text": "world"}' in out
    assert out.rstrip().endswith("[DONE]")


async def test_relay_surfaces_provider_error_then_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: _FakeClient(401, []))
    out = b"".join(
        [chunk async for chunk in ai._relay("anthropic", "m", "k", "", "p", 100)]
    ).decode()
    assert '"error": "anthropic 401"' in out
    assert out.rstrip().endswith("[DONE]")
