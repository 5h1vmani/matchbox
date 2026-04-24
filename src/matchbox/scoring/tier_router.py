"""Tier router — maps scored jobs to tailor paths.

Tiers:
  bespoke   — high-score dream-tier roles; full LLM content generation
  template  — mid-score; anchor-pack selection + lighter LLM call
  canonical — low-score; pre-rendered PDF, copy at submission time
  skip      — below minimum threshold or excluded
"""

from __future__ import annotations

from matchbox.core.schema import Job, Person

# Score thresholds (lower bound inclusive) — matches shared/rubric.yaml
_TIER_THRESHOLDS = {
    "bespoke": 0.80,
    "template": 0.60,
    "canonical": 0.40,
}


def route_job(job: Job, person: Person) -> str:
    """Return the tailor tier for this job."""
    # Exclusions are always skip
    if job.exclusion_triggered or job.state == "skip":
        return "skip"

    score = job.total_score
    if score is None:
        return "canonical"

    # Normalise from 0-5 to 0-1
    normalised = score / 5.0

    if normalised >= _TIER_THRESHOLDS["bespoke"]:
        return "bespoke"
    if normalised >= _TIER_THRESHOLDS["template"]:
        return "template"
    if normalised >= _TIER_THRESHOLDS["canonical"]:
        return "canonical"
    return "skip"


def infer_geo(country: str | None) -> str:
    """Map job country string to geo variant: 'uk' | 'india' | 'relocate'."""
    if not country:
        return "relocate"
    c = country.lower().strip()
    if c in {"uk", "united kingdom", "gb", "britain", "england"}:
        return "uk"
    if c in {"india", "in", "ind"}:
        return "india"
    return "relocate"
