"""Tier-2 deterministic enrichment: conservative by design (unknown unless explicit)."""

from __future__ import annotations

from matchbox.discovery import enrich


def test_dedup_key_prefers_url() -> None:
    assert enrich.dedup_key("https://J/1", "Acme", "Eng", "Pune") == "https://j/1"
    assert enrich.dedup_key(None, "Acme", "Eng", "Pune") == "acme|eng|pune"
    assert enrich.dedup_key("  ", "Acme", "Eng") == "acme|eng|"


def test_seniority_from_title() -> None:
    assert enrich.parse_seniority("Senior Backend Engineer") == "senior"
    assert enrich.parse_seniority("Staff Software Engineer") == "staff"
    assert enrich.parse_seniority("Principal Engineer") == "principal"
    assert enrich.parse_seniority("Engineering Intern") == "intern"
    assert enrich.parse_seniority("Junior Developer") == "junior"
    assert enrich.parse_seniority("Lead Data Engineer") == "lead"
    # No explicit signal -> None (we do not guess 'mid').
    assert enrich.parse_seniority("Software Engineer") is None


def test_min_years() -> None:
    assert enrich.parse_min_years("5+ years of experience required") == 5
    assert enrich.parse_min_years("10 years Python, 3 yrs Go") == 3  # the minimum bar
    assert enrich.parse_min_years("No numbers here") is None
    assert enrich.parse_min_years(None) is None


def test_sponsorship_is_high_precision() -> None:
    assert enrich.parse_eligibility("We are unable to sponsor visas")["sponsorship"] == "none"
    assert enrich.parse_eligibility("No visa sponsorship available")["sponsorship"] == "none"
    assert enrich.parse_eligibility("Visa sponsorship is available")["sponsorship"] == "offered"
    assert enrich.parse_eligibility("We will sponsor the right candidate")["sponsorship"] == "offered"
    # Silent JD -> unknown, never 'none' (would wrongly hide a viable job).
    assert enrich.parse_eligibility("Great team, great mission.")["sponsorship"] == "unknown"


def test_citizenship_and_clearance_only_when_explicit() -> None:
    e = enrich.parse_eligibility("US citizens only. Active security clearance required.")
    assert e["citizenship_required"] == 1
    assert e["clearance_required"] == 1
    silent = enrich.parse_eligibility("Build great software with us.")
    assert silent["citizenship_required"] is None
    assert silent["clearance_required"] is None


def test_remote_scope() -> None:
    assert enrich.parse_remote_scope("This is a remote (US) position") == "us"
    assert enrich.parse_remote_scope("Remote within India only") == "india"
    assert enrich.parse_remote_scope("Remote role, work from anywhere") is None


def test_enrich_record_shape() -> None:
    rec = enrich.enrich_record("Senior Engineer", "5+ years. We will sponsor.")
    assert rec["seniority"] == "senior"
    assert rec["min_years_exp"] == 5
    assert rec["sponsorship"] == "offered"
    assert set(rec) == {
        "seniority", "min_years_exp", "sponsorship",
        "citizenship_required", "clearance_required", "remote_scope",
    }
