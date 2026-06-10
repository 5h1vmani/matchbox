"""The metric emphasizer bolds scan-worthy numbers and nothing else."""

from __future__ import annotations

from matchbox.render_html import _emphasize_metrics


def test_bolds_plain_numbers_and_percent() -> None:
    out = _emphasize_metrics("Cut research time by 58 to 60 percent through synthesis.")
    assert "<strong>58</strong>" in out
    assert "<strong>60 percent</strong>" in out


def test_bolds_thousands_separators() -> None:
    out = _emphasize_metrics("Load-tested to 250,000 concurrent users.")
    assert "<strong>250,000</strong>" in out


def test_bolds_currency_and_plus() -> None:
    assert "<strong>INR 1 million</strong>" in _emphasize_metrics("Saved INR 1 million yearly.")
    assert "<strong>150+</strong>" in _emphasize_metrics("Trained 150+ analysts.")


def test_identifiers_are_not_bolded() -> None:
    out = _emphasize_metrics("Used K6 on EC2 with S3 buckets.")
    assert "<strong>" not in out


def test_escaping_still_applies() -> None:
    out = _emphasize_metrics("R&D spend down 90%")
    assert "R&amp;D" in out
    assert "<strong>90%</strong>" in out


def test_word_numbers_untouched() -> None:
    out = _emphasize_metrics("Cut scoring from seven to ten minutes down to two to three.")
    assert "<strong>" not in out
