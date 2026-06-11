"""Brain-supplied selection: schema validation, library/voice validation, and
the one-page word-budget trim. The no-fabrication guarantee lives in
_apply_selection (every id must be a verified library bullet). Extracted from
assemble.py."""

from __future__ import annotations

from typing import Any

from matchbox.contracts import validator_for
from matchbox.core.logging import get_logger
from matchbox.matching.select import DEFAULT_WORD_BUDGET, Component
from matchbox.polish import load_voice_rules, validate_voice

log = get_logger(__name__)


def validate_selection_payload(payload: dict[str, Any]) -> list[str]:
    """Schema-validate a brain selection payload. Returns human-readable errors
    (empty when valid)."""
    return [e.message for e in validator_for("selection.v1.json").iter_errors(payload)]


def _apply_project_selection(
    selection: dict[str, Any], verified_projects: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate the brain's optional project picks against the verified library;
    return the project rows in the brain's order. Same no-fabrication rule as
    bullets: an unknown or unverified id is a loud rejection, never a skip."""
    ids = [int(i) for i in (selection.get("selected_project_ids") or [])]
    if not ids:
        return []
    unknown = [i for i in ids if i not in verified_projects]
    if unknown:
        raise ValueError(
            "selection references ids that are not verified library projects: "
            + ", ".join(map(str, unknown))
        )
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            p = verified_projects[i]
            out.append({"name": p["name"], "text": p["text"], "url": p["url"]})
    return out


def _apply_skill_selection(
    selection: dict[str, Any], library_skills: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate the brain's optional skill picks against the library and return
    skill groups in the brain's order. Category order is the order of first
    appearance in the brain's id list; items within a category keep the brain's
    order. An unknown id is a hard failure with the same error/exit semantics as
    unknown bullet or project ids."""
    ids = [int(i) for i in (selection.get("selected_skill_ids") or [])]
    if not ids:
        return []
    unknown = [i for i in ids if i not in library_skills]
    if unknown:
        raise ValueError(
            "selection references ids that are not library skills: " + ", ".join(map(str, unknown))
        )
    # Group by category, preserving the brain's order (first appearance of a
    # category determines category order; items within a category keep brain order).
    cat_order: list[str] = []
    cat_items: dict[str, list[str]] = {}
    seen: set[int] = set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        skill = library_skills[i]
        cat = skill["category"] or "Other"
        name = skill["name"]
        if cat not in cat_items:
            cat_order.append(cat)
            cat_items[cat] = []
        cat_items[cat].append(name)
    return [{"category": cat, "items": cat_items[cat]} for cat in cat_order]


def _apply_selection(
    selection: dict[str, Any], components: list[Component]
) -> tuple[list[int], dict[int, float], str]:
    """Validate the brain's selection against the verified library and the voice
    gate; return (ordered_ids, rank_relevance, summary).

    The no-fabrication guarantee is enforced HERE, not by selection being an
    algorithm: every id must be a verified library bullet, or we reject loudly.
    The brain emits ids only (never bullet text), so the selected text is
    unmodified by construction. The summary is voice-gated like a cover letter;
    its truthfulness is the brain's responsibility.
    """
    valid = {c.id for c in components}
    ids = [int(i) for i in selection["selected_bullet_ids"]]
    unknown = [i for i in ids if i not in valid]
    if unknown:
        raise ValueError(
            "selection references ids that are not verified library bullets: "
            + ", ".join(map(str, unknown))
        )
    seen: set[int] = set()
    ordered: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)

    summary = str(selection["summary"]).strip()
    violations = validate_voice(summary, load_voice_rules(), scope="summary")
    if violations:
        raise ValueError(
            "summary failed the voice gate: "
            + "; ".join(f"{v.rule}: {v.detail}" for v in violations)
        )

    # Rank-relevance: earlier in the brain's order = more important (drives the
    # changes.md display). Safety belt: keep the brain's order, drop the
    # lowest-priority (trailing) bullets once the body exceeds the word budget
    # scaled by target_pages (1 -> DEFAULT_WORD_BUDGET, 2 -> 2x the budget).
    target_pages = int(selection.get("target_pages") or 1)
    word_budget = DEFAULT_WORD_BUDGET * target_pages
    relevance = {cid: float(len(ordered) - rank) for rank, cid in enumerate(ordered)}
    text_by_id = {c.id: c.text for c in components}
    kept: list[int] = []
    used = 0
    for cid in ordered:
        words = len(text_by_id[cid].split())
        if kept and used + words > word_budget:
            break
        kept.append(cid)
        used += words
    if len(kept) < len(ordered):
        log.info(
            "page-%d budget kept %d of %d selected bullets (dropped %d trailing)",
            target_pages,
            len(kept),
            len(ordered),
            len(ordered) - len(kept),
        )
    return kept, relevance, summary
