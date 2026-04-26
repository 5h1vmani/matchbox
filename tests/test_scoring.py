"""Scoring rubric — weight/dimension alignment + pure-function recombine.

Locks in the fix for the historical bug where comp/cultural/red_flags were
weighted by tech_stack/seniority/location_remote (semantically unrelated).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from matchbox.core.schema import Job, ScoringWeights
from matchbox.scoring.rubric import weighted_total


def _scored_job(**overrides: float | str | None) -> Job:
    base = dict(
        profile_name="t",
        company="X",
        role="Y",
        url="https://example.com/x",
        cv_match_score=4.0,
        company_mission_fit_score=3.0,
        role_mission_fit_score=2.0,
        comp_score=5.0,
        cultural_score=1.0,
        red_flags_score=4.0,
    )
    base.update(overrides)
    return Job(**base)  # type: ignore[arg-type]


class TestWeightedTotal:
    def test_default_weights_sum(self) -> None:
        # 4*0.25 + 3*0.15 + 2*0.15 + 5*0.20 + 1*0.10 + 4*0.10
        # = 1.0 + 0.45 + 0.30 + 1.0 + 0.10 + 0.40 = 3.25
        job = _scored_job()
        assert weighted_total(job, ScoringWeights()) == 3.25

    def test_zero_weights_zero_total(self) -> None:
        weights = ScoringWeights(
            cv_match_weight=0.0,
            company_mission_fit_weight=0.0,
            role_mission_fit_weight=0.0,
            comp_weight=0.0,
            cultural_weight=0.0,
            red_flags_weight=0.0,
        )
        assert weighted_total(_scored_job(), weights) == 0.0

    def test_unscored_job_total_is_zero(self) -> None:
        job = Job(profile_name="t", company="X", role="Y", url="https://example.com/x")
        assert weighted_total(job, ScoringWeights()) == 0.0

    def test_partial_dimensions_sum_only_present(self) -> None:
        job = _scored_job(
            cv_match_score=5.0,
            company_mission_fit_score=None,
            role_mission_fit_score=None,
            comp_score=None,
            cultural_score=None,
            red_flags_score=None,
        )
        assert weighted_total(job, ScoringWeights()) == round(5.0 * 0.25, 2)


class TestScoringWeightsAliases:
    """Backward-compat: legacy YAML keys must still load."""

    def test_canonical_names_work(self) -> None:
        w = ScoringWeights(
            cv_match_weight=0.3,
            company_mission_fit_weight=0.2,
            role_mission_fit_weight=0.1,
            comp_weight=0.2,
            cultural_weight=0.1,
            red_flags_weight=0.1,
        )
        assert w.comp_weight == 0.2
        assert w.cultural_weight == 0.1
        assert w.red_flags_weight == 0.1

    def test_legacy_aliases_still_load(self) -> None:
        w = ScoringWeights.model_validate(
            {
                "cv_match_weight": 0.3,
                "company_mission_fit_weight": 0.2,
                "role_mission_fit_weight": 0.1,
                "tech_stack_weight": 0.25,
                "seniority_weight": 0.05,
                "location_remote_weight": 0.10,
            }
        )
        # Legacy values land in the canonical fields.
        assert w.comp_weight == 0.25
        assert w.cultural_weight == 0.05
        assert w.red_flags_weight == 0.10

    def test_unknown_field_rejected(self) -> None:
        # Defensive: random key shouldn't silently bind anywhere.
        # Pydantic's default ignores extras; this just documents the
        # current behaviour so a future change to extra='forbid'
        # surfaces the test.
        w = ScoringWeights.model_validate({"bogus_weight": 5.0})
        assert not hasattr(w, "bogus_weight")

    def test_negative_weight_rejected_by_business_layer(self) -> None:
        # ScoringWeights itself doesn't bound — the editor does. This
        # locks in that the model will accept anything numeric, so the
        # validation must live at the edge.
        ScoringWeights(cv_match_weight=-1.0)  # no error
        with pytest.raises(ValidationError):
            ScoringWeights(cv_match_weight="not a number")  # type: ignore[arg-type]
