"""PDF backend selection. Exercises the env-driven choice only; the actual
weasyprint render is covered by the assemble smoke tests, and the chromium path
needs a browser binary unavailable in CI."""

from __future__ import annotations

import pytest

import matchbox.pdf_backend as pb


def test_explicit_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHBOX_PDF_BACKEND", "weasyprint")
    assert pb.select_backend() == "weasyprint"


def test_explicit_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHBOX_PDF_BACKEND", "chromium")
    assert pb.select_backend() == "chromium"


def test_auto_prefers_weasyprint_when_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATCHBOX_PDF_BACKEND", raising=False)
    monkeypatch.setattr(pb, "_weasyprint_importable", lambda: True)
    assert pb.select_backend() == "weasyprint"


def test_auto_falls_back_to_chromium_without_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATCHBOX_PDF_BACKEND", raising=False)
    monkeypatch.setattr(pb, "_weasyprint_importable", lambda: False)
    assert pb.select_backend() == "chromium"


def test_unknown_value_is_treated_as_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHBOX_PDF_BACKEND", "garbage")
    monkeypatch.setattr(pb, "_weasyprint_importable", lambda: True)
    assert pb.select_backend() == "weasyprint"
