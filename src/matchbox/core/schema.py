"""Pydantic models — single source of truth for all Matchbox data structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ──────────────────────────────────────────────
# Profile sub-models (what lives in profile.yaml)
# ──────────────────────────────────────────────


class ProfileMeta(BaseModel):
    schema_version: int = 1
    last_updated: str = ""
    matchbox_version: str = "0.2.0"

    @field_validator("last_updated", mode="before")
    @classmethod
    def _coerce_date(cls, v: Any) -> str:
        return str(v) if v else ""


class Candidate(BaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    languages: list[str] = Field(default_factory=list)
    linkedin: str = ""
    github: str = ""
    website: str = ""


class Archetype(BaseModel):
    name: str
    level: str = ""
    fit: str = ""


class DreamTiers(BaseModel):
    tier_1_dream: list[str] = Field(default_factory=list)
    tier_2_target: list[str] = Field(default_factory=list)
    tier_3_watchlist: list[str] = Field(default_factory=list)
    tier_4_exploratory: list[str] = Field(default_factory=list)


class Targets(BaseModel):
    primary_roles: list[str] = Field(default_factory=list)
    archetypes: list[Archetype] = Field(default_factory=list)
    dream_tiers: DreamTiers = Field(default_factory=DreamTiers)


class ExclusionRule(BaseModel):
    global_default: str = "exclude"  # "exclude" | "include"
    overrides: dict[str, str] = Field(default_factory=dict)  # country → "include"|"exclude"


class Filters(BaseModel):
    title_positive: list[str] = Field(default_factory=list)
    title_negative: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclusions: dict[str, ExclusionRule] = Field(default_factory=dict)


class CompRange(BaseModel):
    target: str = ""
    minimum: str = ""


class Compensation(BaseModel):
    india: CompRange = Field(default_factory=CompRange)
    uk: CompRange = Field(default_factory=CompRange)
    us: CompRange = Field(default_factory=CompRange)
    other: CompRange = Field(default_factory=CompRange)


class Constraints(BaseModel):
    visa_status: str = ""
    remote_preference: str = ""
    notice_period: str = ""
    earliest_start: str = ""
    relocation_open: bool = False


class WorkBullet(BaseModel):
    text: str
    tags: list[str] = Field(default_factory=list)
    voice_verified: bool = False
    facts_verified: bool = False


class WorkEntry(BaseModel):
    company: str
    role: str
    dates: str
    tenure_years: float = 0.0
    location: str = ""
    tags: list[str] = Field(default_factory=list)
    bullets: list[WorkBullet] = Field(default_factory=list)
    summary: str = ""


class Skill(BaseModel):
    name: str
    category: str = ""
    evidence: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    status: str = ""
    dates: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    load_test_ccu: int | None = None
    url: str = ""


class ScoringWeights(BaseModel):
    cv_match_weight: float = 0.25
    company_mission_fit_weight: float = 0.15
    role_mission_fit_weight: float = 0.15
    tech_stack_weight: float = 0.20
    seniority_weight: float = 0.15
    location_remote_weight: float = 0.10


class Profile(BaseModel):
    """Top-level profile.yaml model."""

    model_config = ConfigDict(populate_by_name=True)

    meta: ProfileMeta = Field(default_factory=ProfileMeta, alias="_meta")
    candidate: Candidate
    targets: Targets = Field(default_factory=Targets)
    filters: Filters = Field(default_factory=Filters)
    compensation: Compensation = Field(default_factory=Compensation)
    constraints: Constraints = Field(default_factory=Constraints)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)
    work_history: list[WorkEntry] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    role_family_preference: dict[int, str] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# Voice rules (shared + per-person overlay)
# ──────────────────────────────────────────────


class RequiredSignals(BaseModel):
    min_named_entities_per_150_words: int = 3
    min_numbers_per_150_words: int = 2
    min_authenticity_signals: int = 3


class QualityGates(BaseModel):
    max_word_count_cv_bullet: int = 25
    min_word_count_cv_bullet: int = 8
    max_bullets_per_role: int = 5
    min_bullets_per_role: int = 2


class VoiceRules(BaseModel):
    """Fully merged voice rules (shared/voice-rules.yaml + people/{name}/voice.yaml)."""

    no_em_dashes: bool = True
    no_contractions: bool = True
    no_passive_voice: bool = True
    banned_words: list[str] = Field(default_factory=list)
    banned_openers: list[str] = Field(default_factory=list)
    required_signals: RequiredSignals = Field(default_factory=RequiredSignals)
    quality_gates: QualityGates = Field(default_factory=QualityGates)
    # Per-profile: curated example phrasings for the LLM to emulate
    costly_signal_patterns: list[str] = Field(default_factory=list)
    opener_patterns: list[str] = Field(default_factory=list)

    @classmethod
    def merge(cls, defaults: dict[str, Any], overrides: dict[str, Any]) -> VoiceRules:
        """
        Merge shared defaults with per-profile overrides.
        Lists append unless override sets replace: true.
        Maps replace by key.
        """
        merged: dict[str, Any] = dict(defaults)
        for key, val in overrides.items():
            if key == "_meta":
                continue
            if isinstance(val, list) and isinstance(merged.get(key), list):
                replace = overrides.get(f"{key}__replace", False)
                merged[key] = val if replace else (merged[key] + val)
            else:
                merged[key] = val
        # Flatten nested dicts into the top-level for VoiceRules constructor
        flat: dict[str, Any] = {}
        for k, v in merged.items():
            if isinstance(v, dict):
                flat.update(v)
            else:
                flat[k] = v
        return cls.model_validate(flat)


# ──────────────────────────────────────────────
# Person — the fully loaded candidate object
# ──────────────────────────────────────────────


class Person(BaseModel):
    """Fully loaded candidate. Built by core/person.py — never construct directly."""

    name: str
    profile: Profile
    voice: VoiceRules
    stories_text: str = ""


# ──────────────────────────────────────────────
# Pipeline models
# ──────────────────────────────────────────────

VALID_STATES = frozenset(
    {
        "evaluated",
        "queued_for_tailor",
        "tailored",
        "applied",
        "responded",
        "interview",
        "offer",
        "rejected",
        "discarded",
        "skip",
        "cooling",
    }
)

VALID_TIERS = frozenset({"bespoke", "template", "canonical", "skip"})
VALID_GEOS = frozenset({"uk", "india", "relocate"})
VALID_RESPONSE_TYPES = frozenset({"interview", "rejection", "offer", "ghosted", "other"})


class Job(BaseModel):
    """One job posting row. Maps 1:1 to the jobs table."""

    id: int | None = None
    profile_name: str
    scan_run_id: int | None = None
    company: str
    role: str
    location: str | None = None
    country: str | None = None
    url: str
    mode: str | None = None
    ats_source: str | None = None
    posting_date: str | None = None
    discovered_date: str = ""
    jd_summary: str | None = None
    jd_text: str | None = None
    comp_stated: str | None = None
    visa_sponsorship: str | None = None
    legitimacy: str | None = None
    # 6-dimension scoring
    cv_match_score: float | None = None
    company_mission_fit_score: float | None = None
    role_mission_fit_score: float | None = None
    comp_score: float | None = None
    cultural_score: float | None = None
    red_flags_score: float | None = None
    total_score: float | None = None
    recommendation: str | None = None
    report_path: str | None = None
    # Pipeline state
    state: str = "evaluated"
    tier: str | None = None
    tailor_cost_usd: float | None = None
    cv_generated: bool = False
    cover_generated: bool = False
    cv_path: str | None = None
    cover_path: str | None = None
    applied_date: str | None = None
    response_date: str | None = None
    response_type: str | None = None
    response_note: str | None = None
    interview_notes: str | None = None
    rejection_reason: str | None = None
    user_notes: str | None = None
    # UX
    is_starred: bool = False
    role_family: str | None = None
    exclusion_triggered: str | None = None
    dream_tier: str | None = None
    # Link health
    url_last_checked: str | None = None
    url_http_status: int | None = None
    # Audit
    created_at: str | None = None
    updated_at: str | None = None


class Application(BaseModel):
    """One tailored output (CV + cover) per job per tailor run."""

    id: int | None = None
    job_id: int
    profile_name: str
    tier: str
    geo: str
    cv_path: str
    cover_path: str | None = None
    cost_usd: float = 0.0
    content: dict[str, Any] | None = None
    created_at: str | None = None


class Response(BaseModel):
    """One outcome event (interview invite, rejection, offer, etc.)."""

    id: int | None = None
    job_id: int
    profile_name: str
    response_date: str
    response_type: str
    note: str | None = None
    created_at: str | None = None


class ScanRun(BaseModel):
    """One scan execution (daily, funded, dream, etc.)."""

    id: int | None = None
    profile_name: str
    mode: str | None = None
    country: str | None = None
    started_at: str = ""
    completed_at: str | None = None
    raw_candidates: int = 0
    filtered_survivors: int = 0
    scored_count: int = 0
    apply_count: int = 0
    review_count: int = 0
    skip_count: int = 0
    cost_usd: float = 0.0
    status: str = "running"
    notes: str | None = None
    is_trial: bool = False
