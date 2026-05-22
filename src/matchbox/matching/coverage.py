"""Two coverage metrics, per section 5c of v0.3-design.md.

1. Semantic coverage — for each must-have requirement, is it genuinely
   supported by a selected component (similarity above a floor)?

2. ATS keyword presence — a literal, case-insensitive substring check
   against the rendered PDF text. Predicts what a keyword-based ATS
   would find. Accepts variants per term.

Both are reported alongside each tailored CV.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from matchbox.matching.select import Requirement


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
            pattern = r"\b" + re.escape(term.lower()) + r"\b"
            if re.search(pattern, haystack):
                match = term
                break
        out.append(
            KeywordPresenceResult(
                requirement_text=r.text,
                matched_term=match,
                present=match is not None,
            )
        )
    return out
