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
