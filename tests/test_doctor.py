"""Tests for the environment doctor (first-run diagnostics)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import matchbox.web.app as web_app
from matchbox.doctor import Check, checks, main

EXPECTED_NAMES = [
    "python",
    "pdf rendering",
    "node + npm",
    "spa built",
    "claude cli",
    "active profile",
]


def _by_name(results: list[Check], name: str) -> Check:
    return next(check for check in results if check.name == name)


def test_checks_returns_all_six_entries() -> None:
    results = checks()
    assert [check.name for check in results] == EXPECTED_NAMES


def test_python_check_passes_on_supported_interpreter() -> None:
    # The suite itself requires 3.12, so this must hold wherever tests run.
    assert _by_name(checks(), "python").ok is True


def test_spa_check_follows_index_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(web_app, "STATIC_DIR", tmp_path)

    missing = _by_name(checks(), "spa built")
    assert missing.ok is False
    assert missing.required is False
    assert "npm run build" in missing.detail

    index = tmp_path / "app" / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<html></html>")
    assert _by_name(checks(), "spa built").ok is True


def test_absent_binaries_do_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)

    results = checks()  # must not raise with nothing on PATH
    assert _by_name(results, "claude cli").ok is False
    assert _by_name(results, "node + npm").ok is False


def test_main_returns_int(capsys: pytest.CaptureFixture[str]) -> None:
    code = main()
    assert isinstance(code, int)
    out = capsys.readouterr().out
    assert "python" in out
