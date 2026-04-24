"""Tests for core/person.py — Person loader integration tests.

These tests load the real people/shiva/ profile. They require the repo to be
installed (`pip install -e .`) and people/shiva/ to exist on disk.

All facts asserted here are locked in the v0.2 plan's "Critical facts" section.
If any assertion fails, check profile.yaml — do NOT change the assertion.
"""

from __future__ import annotations

import pytest

from matchbox.core.person import load_person
from matchbox.core.schema import Person


@pytest.fixture(scope="module")
def shiva() -> Person:
    return load_person("shiva")


class TestShivaProfileLoads:
    def test_person_object_type(self, shiva: Person) -> None:
        assert isinstance(shiva, Person)

    def test_name(self, shiva: Person) -> None:
        assert shiva.name == "shiva"

    def test_full_name(self, shiva: Person) -> None:
        assert shiva.profile.candidate.full_name == "Shiva Padakanti"

    def test_location(self, shiva: Person) -> None:
        assert "Hyderabad" in shiva.profile.candidate.location

    def test_languages(self, shiva: Person) -> None:
        langs = [lang.lower() for lang in shiva.profile.candidate.languages]
        assert any("telugu" in lang for lang in langs)
        assert any("hindi" in lang for lang in langs)
        assert any("english" in lang for lang in langs)

    def test_voice_rules_loaded(self, shiva: Person) -> None:
        assert shiva.voice.no_em_dashes is True
        assert shiva.voice.no_contractions is True
        assert len(shiva.voice.banned_words) > 0

    def test_stories_loaded(self, shiva: Person) -> None:
        assert len(shiva.stories_text) > 0
        assert "optometrist" in shiva.stories_text.lower()


class TestShivaCriticalFacts:
    """
    Locked facts from plan section "Critical facts locked for Shiva's identity".
    These must never be corrupted during migration or future edits.
    """

    def test_ntt_data_tenure_exactly_2_years(self, shiva: Person) -> None:
        ntt = next(e for e in shiva.profile.work_history if "NTT DATA" in e.company)
        assert ntt.tenure_years == 2.0, (
            "NTT DATA tenure must be exactly 2 years (Jun 2022 – Jun 2024). "
            "Do not state '4 years' anywhere."
        )

    def test_ntt_data_dates(self, shiva: Person) -> None:
        ntt = next(e for e in shiva.profile.work_history if "NTT DATA" in e.company)
        assert "2022" in ntt.dates
        assert "2024" in ntt.dates

    def test_pinaka_ccu(self, shiva: Person) -> None:
        pinaka = next(p for p in shiva.profile.projects if p.name == "Pinaka")
        assert pinaka.load_test_ccu == 250000

    def test_ntt_data_user_count_in_bullets(self, shiva: Person) -> None:
        ntt = next(e for e in shiva.profile.work_history if "NTT DATA" in e.company)
        all_bullet_text = " ".join(b.text for b in ntt.bullets)
        assert "150" in all_bullet_text, "NTT DATA bullets must mention 150+ users trained"
        assert "30" in all_bullet_text, "NTT DATA bullets must mention 30 entities"

    def test_isha_dates(self, shiva: Person) -> None:
        isha = next(e for e in shiva.profile.work_history if "Isha" in e.company)
        assert "2024" in isha.dates
        assert "2025" in isha.dates

    def test_dream_tiers_populated(self, shiva: Person) -> None:
        tiers = shiva.profile.targets.dream_tiers
        assert "Anthropic" in tiers.tier_1_dream
        assert len(tiers.tier_2_target) > 10

    def test_exclusions_present(self, shiva: Person) -> None:
        excl = shiva.profile.filters.exclusions
        assert "crypto" in excl
        assert excl["crypto"].global_default == "exclude"

    def test_defense_override_india(self, shiva: Person) -> None:
        excl = shiva.profile.filters.exclusions
        assert "defense" in excl
        assert excl["defense"].overrides.get("india") == "include"

    def test_compensation_india_floor(self, shiva: Person) -> None:
        comp = shiva.profile.compensation
        assert "35" in comp.india.minimum

    def test_role_family_preference_sa_first(self, shiva: Person) -> None:
        rfp = shiva.profile.role_family_preference
        assert rfp[1] == "solutions_architect_startups"

    def test_schema_version(self, shiva: Person) -> None:
        meta = shiva.profile.meta
        assert meta.schema_version == 1
