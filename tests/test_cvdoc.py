"""Experience date-key parsing: free-text and ISO both sort correctly."""

from __future__ import annotations

from matchbox.assemble_parts.cvdoc import _exp_date_key


def test_freetext_month_year() -> None:
    assert _exp_date_key("Aug 2025") == (2025, 8)


def test_bare_year() -> None:
    assert _exp_date_key("2014") == (2014, 0)


def test_present_and_empty_sort_newest() -> None:
    assert _exp_date_key("present") == (9999, 13)
    assert _exp_date_key("") == (9999, 13)
    assert _exp_date_key(None) == (9999, 13)


def test_iso_full_date_keeps_month() -> None:
    # Regression: ISO dates used to collapse to (0, 0), losing year and month.
    assert _exp_date_key("2024-08-01") == (2024, 8)


def test_iso_year_month() -> None:
    assert _exp_date_key("2024-08") == (2024, 8)


def test_iso_orders_within_same_year() -> None:
    assert _exp_date_key("2024-08-01") > _exp_date_key("2024-03-01")


def test_unparsable_sinks_to_zero() -> None:
    assert _exp_date_key("sometime last year") == (0, 0)
