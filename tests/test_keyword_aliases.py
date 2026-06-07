"""Alias-aware keyword presence: safe synonyms match, truth boundary holds."""

from __future__ import annotations

from matchbox.matching.coverage import (
    check_keyword_presence,
    coverage_band,
    expand_aliases,
    summarize_coverage,
)
from matchbox.matching.select import Requirement


def test_coverage_band_three_states() -> None:
    f = 0.5
    assert coverage_band(selected_best=0.7, library_best=0.7, floor=f) == "covered"
    # nothing selected clears it, but the library does -> partial
    assert coverage_band(selected_best=0.2, library_best=0.6, floor=f) == "partial"
    assert coverage_band(selected_best=0.1, library_best=0.2, floor=f) == "uncovered"


def test_summarize_coverage_counts_only_covered_band() -> None:
    cov = {
        "semantic": {
            "must_haves": [
                {"text": "a", "band": "covered"},
                {"text": "b", "band": "partial"},
                {"text": "c", "band": "uncovered"},
            ]
        }
    }
    assert summarize_coverage(cov) == {"covered": 1, "total": 3}
    # Pre-band artifacts (bare boolean) still summarize.
    legacy = {"semantic": {"must_haves": [{"text": "a", "covered": True}]}}
    assert summarize_coverage(legacy) == {"covered": 1, "total": 1}
    assert summarize_coverage({"semantic": {"must_haves": []}}) is None
    assert summarize_coverage(None) is None


def _req(text: str, keywords: list[str] | None = None) -> Requirement:
    return Requirement(text=text, type="must-have", keywords=keywords or [], variants=[])


def test_expand_aliases_includes_synonyms() -> None:
    al = expand_aliases("kubernetes")
    assert "kubernetes" in al
    assert "k8s" in al


def test_expand_aliases_unknown_term_is_itself() -> None:
    assert expand_aliases("cobol") == ["cobol"]


def test_alias_satisfies_requirement() -> None:
    # JD asks for "kubernetes"; the CV says "k8s" -> covered.
    res = check_keyword_presence(
        "Built infrastructure with k8s and Terraform.",
        [_req("Kubernetes experience", ["kubernetes"])],
    )
    assert res[0].present
    assert res[0].matched_term == "k8s"  # the exact string found in the CV


def test_truth_boundary_no_cross_cloud() -> None:
    # JD asks for Azure; the CV only has AWS. Different groups -> NOT covered.
    res = check_keyword_presence(
        "Deep AWS experience across Lambda and S3.",
        [_req("Azure experience", ["azure"])],
    )
    assert not res[0].present
    assert res[0].matched_term is None


def test_word_boundary_preserved() -> None:
    # "k8s" must not match inside "k8some".
    res = check_keyword_presence(
        "We use k8some proprietary tool.",
        [_req("Kubernetes", ["kubernetes"])],
    )
    assert not res[0].present


def test_symbol_term_matches_via_lookaround() -> None:
    res = check_keyword_presence("Strong c++ background.", [_req("C++", ["c++"])])
    assert res[0].present
