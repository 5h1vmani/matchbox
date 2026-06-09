"""Brain-supplied selection: schema validation, library/voice validation, and
the one-page word-budget trim. The no-fabrication guarantee lives in
_apply_selection (every id must be a verified library bullet). Extracted from
assemble.py."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator

from matchbox.core.db import PROJECT_ROOT
from matchbox.core.logging import get_logger
from matchbox.matching.select import DEFAULT_WORD_BUDGET, Component
from matchbox.polish import load_voice_rules, validate_voice

_SCHEMAS_DIR = PROJECT_ROOT / "schemas"

log = get_logger(__name__)


def _selection_validator() -> Draft202012Validator:
    schema = json.loads((_SCHEMAS_DIR / "selection.v1.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_selection_payload(payload: dict[str, Any]) -> list[str]:
    """Schema-validate a brain selection payload. Returns human-readable errors
    (empty when valid)."""
    return [e.message for e in _selection_validator().iter_errors(payload)]


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
    # changes.md display). One-page safety belt: keep the brain's order, drop the
    # lowest-priority (trailing) bullets once the body exceeds the word budget.
    relevance = {cid: float(len(ordered) - rank) for rank, cid in enumerate(ordered)}
    text_by_id = {c.id: c.text for c in components}
    kept: list[int] = []
    used = 0
    for cid in ordered:
        words = len(text_by_id[cid].split())
        if kept and used + words > DEFAULT_WORD_BUDGET:
            break
        kept.append(cid)
        used += words
    if len(kept) < len(ordered):
        log.info(
            "one-page budget kept %d of %d selected bullets (dropped %d trailing)",
            len(kept),
            len(ordered),
            len(ordered) - len(kept),
        )
    return kept, relevance, summary
