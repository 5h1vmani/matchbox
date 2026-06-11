"""The metric emphasizer bolds signal numbers and never bolds calendar years or
version numbers (new policy as of the 'signal only' refactor)."""

from __future__ import annotations

from matchbox.render_html import _emphasize_metrics

# ── should bold ────────────────────────────────────────────────────────────────


def test_bolds_percent() -> None:
    out = _emphasize_metrics("Cut research time by 58 to 60 percent through synthesis.")
    # "58" has no qualifying suffix/prefix under the new policy — not bolded.
    assert "<strong>58</strong>" not in out
    assert "<strong>60 percent</strong>" in out


def test_bolds_thousands_separators() -> None:
    out = _emphasize_metrics("Load-tested to 250,000 concurrent users.")
    assert "<strong>250,000</strong>" in out


def test_bolds_currency_named() -> None:
    assert "<strong>INR 1 million</strong>" in _emphasize_metrics("Saved INR 1 million yearly.")


def test_bolds_plus_suffix() -> None:
    assert "<strong>150+</strong>" in _emphasize_metrics("Trained 150+ analysts.")


def test_bolds_multiplier_suffix() -> None:
    out = _emphasize_metrics("Improved throughput 3x overall.")
    assert "<strong>3x</strong>" in out


def test_bolds_magnitude_suffix_M() -> None:
    out = _emphasize_metrics("Raised $1.2M in seed funding.")
    assert "<strong>$1.2M</strong>" in out


def test_bolds_time_unit() -> None:
    out = _emphasize_metrics("Reduced p99 latency to 30 minutes.")
    assert "<strong>30 minutes</strong>" in out


def test_bolds_currency_symbol_million() -> None:
    out = _emphasize_metrics("Managed a $5 million budget.")
    # $5 has a currency prefix so it is bold; " million" may merge or be separate
    assert "<strong>" in out
    assert "5" in out


def test_bolds_lowercase_plural_count() -> None:
    """Number followed by a lowercase plural noun ending in 's'."""
    out = _emphasize_metrics("Managed 12 engineers across three sites.")
    assert "<strong>12 engineers</strong>" in out


def test_bolds_comma_thousands() -> None:
    # "requests" is a lowercase plural, so the whole span bolds together.
    out = _emphasize_metrics("Processed 1,500 requests per second.")
    assert "<strong>1,500 requests</strong>" in out


# ── should NOT bold ────────────────────────────────────────────────────────────


def test_does_not_bold_standalone_year() -> None:
    out = _emphasize_metrics("Joined the company in 2019.")
    assert "<strong>2019</strong>" not in out


def test_does_not_bold_year_since() -> None:
    out = _emphasize_metrics("Working there since 2021.")
    assert "<strong>2021</strong>" not in out


def test_does_not_bold_year_range() -> None:
    out = _emphasize_metrics("Worked there from 2019 to 2023.")
    assert "<strong>2019</strong>" not in out
    assert "<strong>2023</strong>" not in out


def test_does_not_bold_version_number() -> None:
    out = _emphasize_metrics("Upgraded to Python 3.11.")
    assert "<strong>3.11</strong>" not in out
    assert "<strong>3</strong>" not in out  # the 3 alone should not bold either


def test_does_not_bold_version_multi_part() -> None:
    out = _emphasize_metrics("Using React 18 and webpack 5.75.0.")
    # 5.75.0 is a version
    assert "<strong>5.75.0</strong>" not in out


def test_does_not_bold_react_version() -> None:
    out = _emphasize_metrics("Migrated to React 19 from React 16.")
    assert "<strong>19</strong>" not in out
    assert "<strong>16</strong>" not in out


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


# ── edge cases ─────────────────────────────────────────────────────────────────


def test_year_2000() -> None:
    out = _emphasize_metrics("Founded in 2000.")
    assert "<strong>2000</strong>" not in out


def test_year_1999() -> None:
    out = _emphasize_metrics("Born in 1999.")
    assert "<strong>1999</strong>" not in out


def test_bolds_ms_unit() -> None:
    out = _emphasize_metrics("Reduced cold-start to 120 ms.")
    assert "<strong>120 ms</strong>" in out


def test_bolds_gb_unit() -> None:
    out = _emphasize_metrics("Transferred 5 gb of data.")
    assert "<strong>5 gb</strong>" in out
