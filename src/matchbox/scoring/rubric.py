"""6-dimension scoring rubric.

Reads shared/rubric.yaml for dimension weights and tier thresholds.
Reads profile.yaml:scoring for per-person weight overrides.
All computation is deterministic Python — zero LLM cost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from matchbox.core.schema import Job, Person, ScoringWeights

_yaml = YAML()


def _shared_rubric() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "shared" / "rubric.yaml"
    if not path.exists():
        return {}
    with path.open() as fh:
        data = _yaml.load(fh)
    return dict(data) if data else {}


def _weights(person: Person) -> ScoringWeights:
    return person.profile.scoring


def score_job(job: Job, person: Person, jd_text: str = "") -> Job:
    """
    Compute per-dimension scores and total_score for a job.

    Scores are on 0-5 scale. This is a heuristic scorer:
    - company_mission_fit: from dream_tier baseline
    - role_mission_fit: title keyword match against person's target roles
    - cv_match: keyword overlap between JD and person's skills + tags
    - cultural: placeholder (requires LLM or user input; defaults to 3.0)
    - red_flags: starts at 5.0, deducted for exclusion triggers
    - comp_score: placeholder (requires comp data extraction; defaults to 3.0)

    Phase 3 will replace placeholders with LLM-assisted scoring where needed.
    """
    weights = _weights(person)
    rubric = _shared_rubric()
    tier_baselines: dict[str, float] = {
        "tier_1_dream": 5.0,
        "tier_2_target": 4.0,
        "tier_3_watchlist": 3.0,
        "tier_4_exploratory": 2.5,
    }

    # --- company_mission_fit ---
    dream_tiers = person.profile.targets.dream_tiers
    company_lower = job.company.lower()
    company_tier = None
    for tier_name, companies in {
        "tier_1_dream": dream_tiers.tier_1_dream,
        "tier_2_target": dream_tiers.tier_2_target,
        "tier_3_watchlist": dream_tiers.tier_3_watchlist,
        "tier_4_exploratory": dream_tiers.tier_4_exploratory,
    }.items():
        if any(company_lower in c.lower() for c in companies):
            company_tier = tier_name
            break

    mission_score = tier_baselines.get(company_tier or "tier_4_exploratory", 2.5)
    job = job.model_copy(update={"dream_tier": company_tier})

    # --- role_mission_fit ---
    role_lower = job.role.lower()
    target_roles_lower = [r.lower() for r in person.profile.targets.primary_roles]
    title_pos_lower = [t.lower() for t in person.profile.filters.title_positive]
    role_match = any(
        keyword in role_lower
        for keyword in title_pos_lower + [w for r in target_roles_lower for w in r.split()]
    )
    role_mission = 4.0 if role_match else 2.5

    # --- cv_match ---
    all_skill_names = [s.name.lower() for s in person.profile.skills]
    all_tags: list[str] = []
    for we in person.profile.work_history:
        all_tags.extend(t.lower() for t in we.tags)
    candidate_keywords = set(all_skill_names + all_tags)
    jd_lower = jd_text.lower() if jd_text else (job.jd_summary or "").lower()
    if jd_lower and candidate_keywords:
        overlap = sum(1 for kw in candidate_keywords if kw in jd_lower)
        cv_match = min(5.0, 2.5 + (overlap / max(len(candidate_keywords), 1)) * 5.0)
    else:
        cv_match = 3.0

    # --- red_flags ---
    red_flags = 5.0 if not job.exclusion_triggered else 1.0

    # --- placeholders (LLM or user input needed) ---
    cultural = 3.0
    comp = 3.0

    total = (
        cv_match * weights.cv_match_weight
        + mission_score * weights.company_mission_fit_weight
        + role_mission * weights.role_mission_fit_weight
        + comp * getattr(weights, "tech_stack_weight", 0.20)
        + cultural * getattr(weights, "seniority_weight", 0.10)
        + red_flags * weights.location_remote_weight
    )

    return job.model_copy(update={
        "cv_match_score": round(cv_match, 2),
        "company_mission_fit_score": round(mission_score, 2),
        "role_mission_fit_score": round(role_mission, 2),
        "comp_score": round(comp, 2),
        "cultural_score": round(cultural, 2),
        "red_flags_score": round(red_flags, 2),
        "total_score": round(total, 2),
    })
