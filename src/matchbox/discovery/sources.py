"""ATS source definitions — Greenhouse, Ashby, Lever, and generic."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ATSSource:
    name: str             # "greenhouse" | "ashby" | "lever" | "generic"
    slug: str             # company slug used in the ATS URL
    base_url: str         # jobs listing API endpoint template
    company: str          # display name for the company
    country: str = ""     # "uk" | "india" | "us" | etc.
    sector: str = ""      # for exclusion checks
    extra: dict[str, str] = field(default_factory=dict)


GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
ASHBY_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
LEVER_BASE = "https://api.lever.co/v0/postings/{slug}"


def greenhouse(slug: str, company: str, country: str = "", sector: str = "") -> ATSSource:
    return ATSSource(
        name="greenhouse",
        slug=slug,
        base_url=GREENHOUSE_BASE.format(slug=slug),
        company=company,
        country=country,
        sector=sector,
    )


def ashby(slug: str, company: str, country: str = "", sector: str = "") -> ATSSource:
    return ATSSource(
        name="ashby",
        slug=slug,
        base_url=ASHBY_BASE.format(slug=slug),
        company=company,
        country=country,
        sector=sector,
    )


def lever(slug: str, company: str, country: str = "", sector: str = "") -> ATSSource:
    return ATSSource(
        name="lever",
        slug=slug,
        base_url=LEVER_BASE.format(slug=slug),
        company=company,
        country=country,
        sector=sector,
    )


# Known ATS slugs for tier-1 and tier-2 dream companies.
KNOWN_SOURCES: list[ATSSource] = [
    greenhouse("anthropic", "Anthropic", sector="ai"),
    ashby("cohere", "Cohere", sector="ai"),
    ashby("mistral", "Mistral AI", country="uk", sector="ai"),
    ashby("sarvam-ai", "Sarvam AI", country="india", sector="ai"),
    greenhouse("perplexityai", "Perplexity", sector="ai"),
    greenhouse("langchain", "LangChain", sector="ai"),
    greenhouse("cursor", "Cursor", sector="ai"),
    ashby("decagon", "Decagon", sector="ai"),
    greenhouse("glean", "Glean", sector="ai"),
    ashby("harvey", "Harvey", sector="legal-ai"),
    greenhouse("elevenlabs", "ElevenLabs", sector="ai"),
    greenhouse("modal-labs", "Modal", sector="ai"),
    ashby("replit", "Replit", sector="ai"),
    ashby("lovable", "Lovable", sector="ai"),
    greenhouse("databricks", "Databricks", sector="data"),
    greenhouse("snowflake", "Snowflake", sector="data"),
    greenhouse("stripe", "Stripe", sector="fintech"),
    greenhouse("notion", "Notion", sector="productivity"),
    greenhouse("vercel", "Vercel", sector="devtools"),
    greenhouse("datadog", "Datadog", sector="devtools"),
    greenhouse("figma", "Figma", sector="design"),
]


def source_for_company(company: str) -> ATSSource | None:
    """Find a known source by company name (case-insensitive substring match)."""
    company_lower = company.lower()
    for source in KNOWN_SOURCES:
        if company_lower in source.company.lower() or source.company.lower() in company_lower:
            return source
    return None
