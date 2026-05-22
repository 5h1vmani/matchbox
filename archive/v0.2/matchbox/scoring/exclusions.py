"""Sector exclusion logic — deterministic, zero LLM cost."""

from __future__ import annotations

from matchbox.core.schema import ExclusionRule, Person


def check_exclusion(person: Person, sector: str, country: str) -> tuple[bool, str | None]:
    """
    Return (excluded, trigger_string). trigger is e.g. "crypto" or "defense|uk".
    """
    rule: ExclusionRule | None = person.profile.filters.exclusions.get(sector.lower())
    if rule is None:
        return False, None

    country_lower = country.lower()
    override = rule.overrides.get(country_lower)

    if override == "include":
        return False, None
    if override == "exclude":
        return True, f"{sector}|{country_lower}"

    if rule.global_default == "exclude":
        return True, sector
    return False, None


def filter_by_exclusions(
    person: Person,
    jobs: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Partition jobs into (allowed, excluded). Excluded jobs get exclusion_triggered set."""
    allowed: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for job in jobs:
        sector = str(job.get("sector", ""))
        country = str(job.get("country", ""))
        is_excluded, trigger = check_exclusion(person, sector, country)
        if is_excluded:
            row = dict(job)
            row["exclusion_triggered"] = trigger
            row["state"] = "skip"
            excluded.append(row)
        else:
            allowed.append(job)
    return allowed, excluded
