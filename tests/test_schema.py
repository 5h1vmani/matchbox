"""Unit tests for core/schema.py — all Pydantic models.

Uses fake candidate data only. No real PII.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from matchbox.core.schema import (
    Application,
    Candidate,
    ExclusionRule,
    Filters,
    Job,
    Person,
    Profile,
    ProfileMeta,
    Response,
    ScanRun,
    Targets,
    VoiceRules,
    VALID_STATES,
    VALID_TIERS,
    VALID_GEOS,
    VALID_RESPONSE_TYPES,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _minimal_profile() -> Profile:
    return Profile(
        candidate=Candidate(
            full_name="Test User",
            email="test@example.com",
            phone="+00 0000000000",
            location="Test City",
        )
    )


def _minimal_job(**kwargs) -> Job:
    defaults = dict(
        profile_name="test",
        company="Acme",
        role="Engineer",
        url="https://example.com/job/1",
    )
    defaults.update(kwargs)
    return Job(**defaults)


# ──────────────────────────────────────────────
# TestJob
# ──────────────────────────────────────────────

class TestJob:
    def test_minimal_construction(self) -> None:
        job = _minimal_job()
        assert job.company == "Acme"
        assert job.state == "evaluated"

    def test_default_booleans_are_false(self) -> None:
        job = _minimal_job()
        assert job.cv_generated is False
        assert job.cover_generated is False
        assert job.is_starred is False

    def test_int_columns_coerce_to_bool(self) -> None:
        # SQLite stores booleans as 0/1 integers
        job = Job.model_validate({
            "profile_name": "test",
            "company": "Acme",
            "role": "Engineer",
            "url": "https://example.com/job/1",
            "cv_generated": 1,
            "cover_generated": 0,
            "is_starred": 1,
        })
        assert job.cv_generated is True
        assert job.cover_generated is False
        assert job.is_starred is True

    def test_valid_states(self) -> None:
        for state in VALID_STATES:
            job = _minimal_job(state=state)
            assert job.state == state

    def test_optional_score_fields_default_none(self) -> None:
        job = _minimal_job()
        assert job.total_score is None
        assert job.cv_match_score is None
        assert job.company_mission_fit_score is None

    def test_model_copy_update(self) -> None:
        job = _minimal_job()
        updated = job.model_copy(update={"total_score": 3.75, "tier": "template"})
        assert updated.total_score == 3.75
        assert updated.tier == "template"
        assert job.total_score is None  # original unchanged

    def test_optional_fields_nullable(self) -> None:
        job = _minimal_job(location=None, country=None, jd_text=None)
        assert job.location is None
        assert job.country is None
        assert job.jd_text is None


# ──────────────────────────────────────────────
# TestProfile
# ──────────────────────────────────────────────

class TestProfile:
    def test_minimal_construction(self) -> None:
        p = _minimal_profile()
        assert p.candidate.full_name == "Test User"

    def test_meta_alias(self) -> None:
        """profile.yaml uses _meta key; Profile must accept it via alias."""
        data = {
            "_meta": {"schema_version": 1, "last_updated": "2026-01-01"},
            "candidate": {"full_name": "Test User"},
        }
        p = Profile.model_validate(data)
        assert p.meta.schema_version == 1

    def test_meta_direct_field_name(self) -> None:
        """Accessing via .meta (not ._meta) always works."""
        p = _minimal_profile()
        assert p.meta.schema_version == 1

    def test_date_coercion_in_meta(self) -> None:
        """ruamel.yaml returns datetime.date — must coerce to str."""
        import datetime
        meta = ProfileMeta(last_updated=datetime.date(2026, 4, 24))  # type: ignore[arg-type]
        assert meta.last_updated == "2026-04-24"

    def test_exclusion_rule_defaults(self) -> None:
        rule = ExclusionRule()
        assert rule.global_default == "exclude"
        assert rule.overrides == {}

    def test_exclusion_override(self) -> None:
        rule = ExclusionRule(global_default="exclude", overrides={"india": "include"})
        assert rule.overrides["india"] == "include"

    def test_archetypes_are_objects(self) -> None:
        data = {
            "candidate": {"full_name": "Test User"},
            "targets": {
                "archetypes": [
                    {"name": "Solutions Architect", "level": "Senior", "fit": "primary"}
                ]
            },
        }
        p = Profile.model_validate(data)
        assert p.targets.archetypes[0].name == "Solutions Architect"


# ──────────────────────────────────────────────
# TestVoiceRules
# ──────────────────────────────────────────────

class TestVoiceRules:
    def test_defaults(self) -> None:
        v = VoiceRules()
        assert v.no_em_dashes is True
        assert v.no_contractions is True
        assert v.banned_words == []

    def test_merge_lists_append(self) -> None:
        defaults = {"banned_words": ["leverage", "synergy"], "no_em_dashes": True}
        overrides = {"banned_words": ["utilize"]}
        merged = VoiceRules.merge(defaults, overrides)
        assert "leverage" in merged.banned_words
        assert "utilize" in merged.banned_words

    def test_merge_skips_meta(self) -> None:
        defaults = {"no_em_dashes": True}
        overrides = {"_meta": {"schema_version": 1}, "no_contractions": False}
        merged = VoiceRules.merge(defaults, overrides)
        assert merged.no_contractions is False

    def test_merge_maps_replace_by_key(self) -> None:
        defaults = {"no_em_dashes": True, "no_contractions": True}
        overrides = {"no_em_dashes": False}
        merged = VoiceRules.merge(defaults, overrides)
        assert merged.no_em_dashes is False
        assert merged.no_contractions is True  # untouched


# ──────────────────────────────────────────────
# TestPipelineModels
# ──────────────────────────────────────────────

class TestPipelineModels:
    def test_application_construction(self) -> None:
        app = Application(
            job_id=1,
            profile_name="test",
            tier="template",
            geo="india",
            cv_path="/tmp/cv.pdf",
            cost_usd=0.12,
        )
        assert app.tier == "template"
        assert app.cover_path is None

    def test_response_construction(self) -> None:
        r = Response(
            job_id=1,
            profile_name="test",
            response_date="2026-05-01",
            response_type="interview",
        )
        assert r.response_type == "interview"

    def test_scan_run_construction(self) -> None:
        run = ScanRun(
            profile_name="test",
            started_at="2026-04-24T10:00:00",
            status="success",
        )
        assert run.status == "success"
        assert run.is_trial is False


# ──────────────────────────────────────────────
# TestConstants
# ──────────────────────────────────────────────

class TestConstants:
    def test_valid_states_complete(self) -> None:
        expected = {
            "evaluated", "queued_for_tailor", "tailored", "applied",
            "responded", "interview", "offer", "rejected",
            "discarded", "skip", "cooling",
        }
        assert VALID_STATES == expected

    def test_valid_tiers(self) -> None:
        assert VALID_TIERS == {"bespoke", "template", "canonical", "skip"}

    def test_valid_geos(self) -> None:
        assert VALID_GEOS == {"uk", "india", "relocate"}

    def test_valid_response_types(self) -> None:
        assert VALID_RESPONSE_TYPES == {"interview", "rejection", "offer", "ghosted", "other"}
