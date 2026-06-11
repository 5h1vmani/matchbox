"""Presentation helpers for the Discovery API: source/salary display strings and
JD text -> readable paragraphs. Pure; no DB, no I/O."""

from __future__ import annotations

import re

# ── source / location helpers ──────────────────────────────────────────────────

_ATS_LABEL = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workable": "Workable",
    "smartrecruiters": "SmartRecruiters",
    "recruitee": "Recruitee",
    "teamtailor": "Teamtailor",
    "personio": "Personio",
    "breezy": "Breezy",
    "jazzhr": "JazzHR",
}


def source_label(ats_type: str | None) -> str:
    """A display string for where the role came from. Defaults to careers page."""
    if ats_type:
        return _ATS_LABEL.get(ats_type.lower(), ats_type.capitalize())
    return "Careers page"


# ── salary (honest display string from the stored ad-data columns) ──────────────

# ISO-4217 -> symbol for the common currencies the pollers see. Unknown codes
# fall back to "<CODE> " so we never drop the currency entirely.
_CURRENCY_SYMBOL = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "CAD": "C$",
    "AUD": "A$",
    "SGD": "S$",
}
# Non-annual periods get an explicit suffix; "year" (the common case) reads bare,
# matching the design's "$150–185k".
_PERIOD_SUFFIX = {"hour": "/hr", "day": "/day", "month": "/mo", "week": "/wk"}


def _compact_parts(value: float, currency: str | None) -> tuple[str, str]:
    """Round to a compact figure, returned as (number, unit): lakhs for INR,
    thousands otherwise. Splitting the unit out lets a range share one suffix
    ("$150–185k" rather than "$150k–185k")."""
    n = round(float(value))
    if (currency or "").upper() == "INR" and n >= 100_000:
        lakhs = n / 100_000
        return (f"{lakhs:.0f}" if lakhs == int(lakhs) else f"{lakhs:.1f}"), "L"
    if n >= 1000:
        thousands = n / 1000
        return (f"{thousands:.0f}" if thousands == int(thousands) else f"{thousands:.1f}"), "k"
    return str(n), ""


def salary_display(
    salary_min: float | None,
    salary_max: float | None,
    currency: str | None = None,
    period: str | None = None,
) -> str | None:
    """The design's `Role.salary` display string from the stored columns.

    Honest by construction: returns None (undisclosed) unless the ad actually
    reported a figure -- never a guess. A range renders "$150–185k"; a single
    bound renders "$150k"; non-annual periods carry a "/hr"-style suffix.
    """
    if salary_min is None and salary_max is None:
        return None
    sym = _CURRENCY_SYMBOL.get((currency or "").upper(), f"{currency} " if currency else "")
    suffix = _PERIOD_SUFFIX.get((period or "").lower(), "")
    if salary_min is not None and salary_max is not None and salary_min != salary_max:
        lo_num, lo_unit = _compact_parts(salary_min, currency)
        hi_num, hi_unit = _compact_parts(salary_max, currency)
        # Share the unit when both bounds land in the same band; keep both
        # otherwise (e.g. a sub-thousand low vs a thousands high).
        lo = lo_num if lo_unit == hi_unit else f"{lo_num}{lo_unit}"
        return f"{sym}{lo}–{hi_num}{hi_unit}{suffix}"
    value = salary_min if salary_min is not None else salary_max
    assert value is not None
    num, unit = _compact_parts(value, currency)
    return f"{sym}{num}{unit}{suffix}"


# Most historically-ingested JDs were stored by the old stripper as one
# structureless block (no newlines, HTML gone, not re-fetchable). When the stored
# text has nothing to split on, `_reparagraph` rebuilds readable paragraphs:
# break before known section headers, then group the rest into sentence-sized
# paragraphs, word-wrapping any run that has no sentence punctuation (a flattened
# bullet list) so nothing renders as a wall of text. New scans keep real structure
# via core.text.strip_html and never reach this path.

# Distinctive multi-word headers: split before them even without a trailing colon.
_HEADER_TIER1 = (
    r"who we are|who you are|about us|about the team|about the role|about you|"
    r"about the company|what you'?ll do|what you will do|what you will be doing|"
    r"what you'?ll be doing|things you will do|things you'?ll do|what you'?ll bring|"
    r"what you'?ll need|what you bring|what we'?re looking for|what we are looking for|"
    r"what we offer|what'?s in it for you|why you'?ll love|why join us|"
    r"key responsibilities|your responsibilities|in this role|the opportunity|"
    r"your mission|your impact|nice to have|bonus points|must haves?|how we work|"
    r"how to apply|hiring process|interview process|ready to apply|our stack|"
    r"tech stack|our values|perks and benefits|benefits and perks|equal opportunity|"
    r"equal employment"
)
# Generic single words: split only when used as a label (followed by a colon), so
# we never break mid-sentence ("the requirements include ...").
_HEADER_TIER2 = (
    r"responsibilities|requirements|qualifications|benefits|perks|compensation|"
    r"the role|your role"
)
_SECTION_SPLIT_RE = re.compile(
    r"\s+(?=(?:" + _HEADER_TIER1 + r")\b|(?:" + _HEADER_TIER2 + r")\b\s*:)", re.I
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_PARA_TARGET = 300  # aim for paragraphs around this many characters
_PARA_MAX = 460  # a chunk longer than this gets broken down further


def _wrap_words(text: str, target: int) -> list[str]:
    """Break a run with no sentence punctuation (a flattened bullet list) at word
    boundaries into target-sized pieces, so it never renders as a wall."""
    out: list[str] = []
    cur = ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > target:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def _sentence_group(text: str, target: int = _PARA_TARGET) -> list[str]:
    """Group sentences into ~target-sized paragraphs, word-wrapping any single run
    that has no sentence breaks."""
    units: list[str] = []
    for piece in _SENTENCE_SPLIT_RE.split(text):
        units += [piece] if len(piece) <= target + 220 else _wrap_words(piece, target)
    out: list[str] = []
    cur = ""
    for s in units:
        if cur and len(cur) + len(s) > target:
            out.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}".strip() if cur else s
    if cur.strip():
        out.append(cur.strip())
    return out


def _reparagraph(text: str) -> list[str]:
    """Rebuild paragraphs from one flattened block: header breaks first, then
    sentence-sized grouping, so a legacy JD reads as paragraphs, not one blob."""
    out: list[str] = []
    for chunk in _SECTION_SPLIT_RE.split(text):
        chunk = chunk.strip()
        if not chunk:
            continue
        out += [chunk] if len(chunk) <= _PARA_MAX else _sentence_group(chunk)
    return out


def jd_lead(jd_text: str | None) -> str:
    """The first paragraph only -- cheap, for the list teaser. Avoids the full
    `_reparagraph` (which the list would run thousands of times); the drawer pays
    that cost once, in `jd_paragraphs`."""
    if not jd_text or not jd_text.strip():
        return ""
    text = jd_text.replace("\r\n", "\n").strip()
    for sep in ("\n\n", "\n"):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text


def jd_paragraphs(jd_text: str | None) -> list[str]:
    """Split a JD blob into display paragraphs (blank-line separated; falls back
    to single newlines; never empty when there is any text). Legacy rows stored as
    one structureless block are rebuilt with `_reparagraph` so the drawer reads as
    paragraphs instead of a wall."""
    if not jd_text or not jd_text.strip():
        return []
    text = jd_text.replace("\r\n", "\n").strip()
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
    if len(parts) <= 1:
        parts = _reparagraph(text)
    return parts or [text]


def jd_teaser(text: str, limit: int = 200) -> str:
    """A short pulled line for the review card. The list serializes this teaser
    (real JDs are often one unbroken block, so the raw first paragraph is the
    whole posting); the JD drawer fetches the full text via load_one. Cuts at a
    word boundary and appends an ellipsis when trimmed."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
