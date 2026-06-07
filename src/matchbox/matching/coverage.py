"""Two coverage metrics, per section 5c of v0.3-design.md.

1. Semantic coverage — for each must-have requirement, is it genuinely
   supported by a selected component (similarity above a floor)?

2. ATS keyword presence — a literal, case-insensitive substring check
   against the rendered PDF text. Predicts what a keyword-based ATS
   would find. Accepts variants per term.

Both are reported alongside each tailored CV.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from matchbox.matching.select import Requirement

_ALIASES_PATH = Path(__file__).resolve().parents[3] / "shared" / "keyword-aliases.json"


def _load_alias_index() -> dict[str, frozenset[str]]:
    """term (lowercased) -> the full set of safe synonyms it belongs to.

    Safe synonyms only: a JD's "kubernetes" is satisfied by "k8s". Different
    clouds/products are deliberately separate groups, so this never papers
    over a skill the user lacks. See shared/keyword-aliases.json.
    """
    try:
        data = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index: dict[str, frozenset[str]] = {}
    for group in data.get("groups", []):
        members = frozenset(str(t).lower() for t in group if t)
        for term in members:
            index[term] = index.get(term, frozenset()) | members
    return index


_ALIAS_INDEX = _load_alias_index()


def expand_aliases(term: str) -> list[str]:
    """The term plus any safe synonyms (lowercased, original first, deduped)."""
    t = term.lower().strip()
    if not t:
        return []
    group = _ALIAS_INDEX.get(t)
    if group is None:
        return [t]
    return [t, *(m for m in sorted(group) if m != t)]


# ── semantic coverage bands (SSOT for the three-state read) ───────────────────

# Bands, strongest first. `partial` is the honest middle ground: the evidence
# exists in the library, it just is not on this tailored CV (or is not yet
# verified). It is never a gap-filler -- the band keys off real similarity and
# the real `facts_verified` flag, never off invented content.
BAND_COVERED = "covered"
BAND_PARTIAL = "partial"
BAND_UNCOVERED = "uncovered"


def coverage_band(*, selected_best: float, library_best: float, floor: float) -> str:
    """Classify one must-have's coverage from its best similarities.

    - covered:   a *selected* (verified, on-CV) bullet clears the floor.
    - partial:   nothing selected clears it, but some library bullet does --
                 the evidence exists, it just is not on this CV or is unverified.
    - uncovered: nothing in the library reaches the floor.
    """
    if selected_best >= floor:
        return BAND_COVERED
    if library_best >= floor:
        return BAND_PARTIAL
    return BAND_UNCOVERED


def summarize_coverage(coverage: dict[str, Any] | None) -> dict[str, int] | None:
    """Collapse a coverage.json's semantic must-haves into the discovery Role
    bar's `{covered, total}`. Only the `covered` band counts as covered (partial
    is honestly not on the CV yet). None when there are no must-haves to report.

    Tolerates the pre-band shape (a bare `covered` boolean) for old artifacts."""
    sem = (coverage or {}).get("semantic") or {}
    must = sem.get("must_haves") or []
    if not must:
        return None
    covered = sum(1 for m in must if m.get("band") == BAND_COVERED or m.get("covered"))
    return {"covered": covered, "total": len(must)}


@dataclass(slots=True)
class KeywordPresenceResult:
    requirement_text: str
    matched_term: str | None  # the variant (or canonical) that hit, if any
    present: bool


def check_keyword_presence(
    rendered_text: str, requirements: list[Requirement]
) -> list[KeywordPresenceResult]:
    """For each must-have, check whether any of its `keywords` (plus any
    `variants`) appears as a substring in the rendered text. Matching is
    case-insensitive and whole-word-boundary-aware so 'k8s' does not
    falsely match inside 'k8some'.
    """
    haystack = rendered_text.lower()
    out: list[KeywordPresenceResult] = []
    for r in requirements:
        if r.type != "must-have":
            continue
        terms = [t for t in [*r.keywords, *r.variants] if t]
        if not terms:
            # Fall back to the requirement text itself — better than skipping.
            terms = [r.text]
        match = None
        for term in terms:
            if not term:
                continue
            # Alias-aware: a requirement's term is covered if it OR any of its
            # safe synonyms appears. Lookarounds (not \b) so symbol terms like
            # "c++" and "ci/cd" match at their edges too.
            for candidate in expand_aliases(term):
                pattern = r"(?<!\w)" + re.escape(candidate) + r"(?!\w)"
                if re.search(pattern, haystack):
                    match = candidate  # report the exact string the ATS would find
                    break
            if match is not None:
                break
        out.append(
            KeywordPresenceResult(
                requirement_text=r.text,
                matched_term=match,
                present=match is not None,
            )
        )
    return out
