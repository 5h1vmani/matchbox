"""Content generation — ONE Sonnet call per job, structured JSON output.

The tool_use pattern guarantees schema-valid JSON without post-processing.
bespoke tier: full bullet rewrite + tailored cover
template tier: anchor-pack bullet selection + lighter cover (shorter prompt)
canonical tier: no call — handled by paths.py directly
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from matchbox.core.schema import Job, Person
from matchbox.tailor.anchor_packs import select_bullets

log = logging.getLogger(__name__)

# Tool schema — the structured output contract between the LLM and render.py
_CONTENT_TOOL: dict[str, Any] = {
    "name": "generate_application_content",
    "description": (
        "Generate tailored CV bullet points and cover letter content "
        "for a specific job application. Output must be factual — "
        "do NOT invent metrics or experiences not provided in the profile."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "One-line CV headline (role | domain | location), max 80 chars",
            },
            "selected_work_history": {
                "type": "array",
                "description": "Work entries with tailored bullets, most recent first",
                "items": {
                    "type": "object",
                    "properties": {
                        "company":  {"type": "string"},
                        "role":     {"type": "string"},
                        "dates":    {"type": "string"},
                        "location": {"type": "string"},
                        "bullets":  {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "maxItems": 5,
                        },
                    },
                    "required": ["company", "role", "dates", "bullets"],
                },
            },
            "selected_projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string"},
                        "description": {"type": "string"},
                        "tags":        {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "description"],
                },
            },
            "cover_opening": {
                "type": "string",
                "description": "First paragraph of cover letter — must NOT start with banned openers",
            },
            "cover_body": {
                "type": "array",
                "description": "2–3 middle paragraphs",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 3,
            },
            "cover_closing": {
                "type": "string",
                "description": "Closing paragraph — one sentence, no platitudes",
            },
        },
        "required": [
            "headline",
            "selected_work_history",
            "cover_opening",
            "cover_body",
            "cover_closing",
        ],
    },
}


def generate_content(
    job: Job,
    person: Person,
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Call the Anthropic API to generate tailored application content.

    Returns the structured content dict (validated against _CONTENT_TOOL schema).
    Raises anthropic.APIError on API failures.
    """
    tier = job.tier or "template"
    if tier == "canonical":
        raise ValueError("generate_content called for canonical tier — use paths.py dispatch")

    prompt = _build_prompt(job, person, tier)
    log.info("content_gen tier=%s company=%s model=%s", tier, job.company, model)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[_CONTENT_TOOL],
        tool_choice={"type": "tool", "name": "generate_application_content"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_use_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    if tool_use_block is None:
        raise RuntimeError("LLM did not return tool_use block — check prompt or model")

    content: dict[str, Any] = tool_use_block.input  # type: ignore[union-attr]
    cost = _estimate_cost(response, model)
    log.info(
        "content_gen done input_tokens=%d output_tokens=%d est_cost_usd=%.4f",
        response.usage.input_tokens,
        response.usage.output_tokens,
        cost,
    )
    content["_meta"] = {
        "tier": tier,
        "model": model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": cost,
    }
    return content


def _build_prompt(job: Job, person: Person, tier: str) -> str:
    p = person.profile
    voice = person.voice

    # Candidate identity block
    identity = (
        f"Full name: {p.candidate.full_name}\n"
        f"Location: {p.candidate.location}\n"
        f"LinkedIn: {p.candidate.linkedin}\n"
        f"GitHub: {p.candidate.github}\n"
    )

    # Work history block
    work_lines: list[str] = []
    for we in p.work_history:
        work_lines.append(f"\n## {we.company} — {we.role} ({we.dates})")
        for b in we.bullets:
            work_lines.append(f"  - {b.text}")

    # Skills
    skills_str = ", ".join(s.name for s in p.skills[:20])

    # JD text (truncate to keep prompt lean)
    jd = (job.jd_text or job.jd_summary or "")[:3000]

    # Voice rules summary
    banned = ", ".join(voice.banned_words[:15])
    banned_openers_str = "\n  ".join(voice.banned_openers[:6])

    # Anchor bullets for template tier
    anchor_note = ""
    if tier == "template":
        role_family = str(list(p.role_family_preference.values())[0]) if p.role_family_preference else None
        anchors = select_bullets(person, role_family, max_per_role=3)
        if anchors:
            anchor_lines = "\n".join(f"  - {b.text}" for b in anchors[:10])
            anchor_note = (
                f"\n\n## Approved anchor bullets (prefer these for template tier)\n{anchor_lines}"
            )

    prompt_lines = [
        "You are a precise CV and cover letter writer. Your output is used verbatim — do NOT hallucinate.",
        "",
        f"## Target role\nCompany: {job.company}\nTitle: {job.role}\nLocation: {job.location or 'n/a'}",
        f"Tier: {tier} ({'full tailoring' if tier == 'bespoke' else 'anchor-pack selection'})",
        "",
        "## JD text",
        jd or "(no JD text available — write based on role title and company)",
        "",
        "## Candidate identity",
        identity,
        "",
        "## Work history",
        *work_lines,
        "",
        "## Skills",
        skills_str,
        anchor_note,
        "",
        "## Voice rules (hard constraints)",
        f"BANNED WORDS (never use): {banned}",
        f"BANNED OPENERS (cover_opening must NOT start with):\n  {banned_openers_str}",
        "No em dashes (—). No contractions (don't, can't, etc.).",
        "Each CV bullet: 8–25 words. Lead with strong verb. Include at least one number.",
        "Cover letter: direct, specific, no platitudes. No 'I am excited to apply'.",
        "",
        "## Stories / prose context",
        person.stories_text[:1500] if person.stories_text else "(none)",
        "",
        "## Task",
        f"Generate tailored application content for {job.role} at {job.company}.",
        "Call the generate_application_content tool with your output.",
    ]

    return "\n".join(line for line in prompt_lines if line is not None)


def _estimate_cost(response: anthropic.types.Message, model: str) -> float:
    """Rough cost estimate from token counts. Prices as of 2026-04."""
    prices: dict[str, tuple[float, float]] = {
        "claude-sonnet-4-6":   (3.0,  15.0),   # per M tokens: input, output
        "claude-opus-4-7":     (15.0, 75.0),
        "claude-haiku-4-5":    (0.25,  1.25),
    }
    in_price, out_price = prices.get(model, (3.0, 15.0))
    cost = (
        response.usage.input_tokens * in_price / 1_000_000
        + response.usage.output_tokens * out_price / 1_000_000
    )
    return round(cost, 6)
