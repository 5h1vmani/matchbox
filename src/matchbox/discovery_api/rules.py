"""Pure Discovery rules — the score_breakdown_json -> Role mapping, membership,
and the queue sort order. SSOT for the Python side; no DB, no I/O.

The crux is mapping our scoring artifacts onto the design's fixed `Role` reads:

* **fit.level** (`strong | good | stretch`) from the scorer's `band`
  (`strong | stretch | weak | skip`), order-preserving, with a numeric `score`
  fallback when the band is missing. The design has three visible buckets; the
  scorer has four, so `stretch` collapses to the design's middle ("good") and the
  genuinely weak/skip roles collapse to the design's lowest ("A stretch").
* **fit.reason** — the scorer's own top-weighted dimension reason, verbatim.
* **eligibility.status** (`eligible | unclear | ineligible`) reconciled from the
  strict-India judge's enum (`eligible | stretch | not_eligible`) in
  `score_breakdown_json["eligibility"]`; absent -> `unclear` (honest default —
  we never claim eligibility the judge did not assert).
* **freshness** from the stored `freshness`/`closes_at` columns, defaulting to
  `open` (the verify_open population job is out of scope for this build).
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

# ── fit ────────────────────────────────────────────────────────────────────────

# Numeric thresholds, used only when `band` is absent. Calibrated against the
# observed score-per-band distribution in a live DB (strong avg ~0.83, stretch
# band ~0.65–0.80, weak ~0.67, skip <0.66).
FIT_STRONG_MIN = 0.74
FIT_GOOD_MIN = 0.66

# Scorer band -> design fit level (order-preserving, 4 -> 3 buckets).
_BAND_TO_FIT = {
    "strong": "strong",
    "stretch": "good",
    "weak": "stretch",
    "skip": "stretch",
}

# Dimension display weighting: the highest-weight dimension whose score is
# meaningful supplies the one-line reason.


def fit_level(score: float | None, band: str | None) -> str:
    """`strong | good | stretch` — band first (authoritative), else score."""
    if band:
        mapped = _BAND_TO_FIT.get(band.lower())
        if mapped:
            return mapped
    s = score or 0.0
    if s >= FIT_STRONG_MIN:
        return "strong"
    if s >= FIT_GOOD_MIN:
        return "good"
    return "stretch"


def fit_reason(breakdown: dict[str, Any] | None) -> str:
    """An honest one-liner from the scorer's own dimensions (never invented).

    Picks the highest-weight dimension that carries a non-trivial score and a
    reason; returns its reason verbatim. Empty when the breakdown has none.
    """
    if not breakdown:
        return ""
    dims = breakdown.get("dimensions")
    if not isinstance(dims, list):
        return ""
    best: tuple[float, str] | None = None
    for d in dims:
        if not isinstance(d, dict):
            continue
        reason = d.get("reason")
        if not reason:
            continue
        weight = float(d.get("weight") or 0.0)
        contrib = weight * float(d.get("score") or 0.0)
        if best is None or contrib > best[0]:
            best = (contrib, str(reason))
    return best[1] if best else ""


# ── eligibility ────────────────────────────────────────────────────────────────

# Strict-India judge enum -> design eligibility status.
_ELIG_STATUS = {
    "eligible": "eligible",
    "likely_eligible": "eligible",
    "stretch": "unclear",
    "unclear": "unclear",
    "not_eligible": "ineligible",
    "ineligible": "ineligible",
    "likely_ineligible": "ineligible",
}


def eligibility(breakdown: dict[str, Any] | None) -> dict[str, str]:
    """`{status, reason}` reconciled to `eligible | unclear | ineligible`.

    Absent judge output -> `unclear` with an empty reason (no fabrication).
    """
    elig = (breakdown or {}).get("eligibility")
    if not isinstance(elig, dict):
        return {"status": "unclear", "reason": ""}
    raw = str(elig.get("status", "")).lower()
    status = _ELIG_STATUS.get(raw, "unclear")
    return {"status": status, "reason": str(elig.get("reason", ""))}


def deterministic_ineligible(
    *,
    sponsorship: str | None,
    citizenship_required: int | None,
    clearance_required: int | None,
    work_auth: dict[str, Any] | None,
) -> dict[str, str] | None:
    """A hard, no-LLM INELIGIBLE verdict from the job's Tier-2 signals vs the
    user's work authorization -- or None when nothing rules the role out.

    This is the eligibility-at-scale lever: it runs on every scored job without
    an LLM. It only ever proves INELIGIBLE (a concrete conflict); it never
    asserts 'eligible' -- that remains the judge's job, and absence of a conflict
    stays 'unclear'. Truthful by construction: we hide a role only on an explicit
    signal the user cannot meet.
    """
    wa = work_auth or {}
    needs_sponsorship = bool(wa.get("needs_sponsorship"))
    has_clearance = bool(wa.get("has_clearance"))
    if sponsorship == "none" and needs_sponsorship:
        return {"status": "ineligible", "reason": "No visa sponsorship, which you need."}
    if citizenship_required and needs_sponsorship:
        return {
            "status": "ineligible",
            "reason": "Citizenship required; you would need sponsorship.",
        }
    if clearance_required and not has_clearance:
        return {
            "status": "ineligible",
            "reason": "Security clearance required, which you do not hold.",
        }
    return None


def eligibility_status(
    breakdown: dict[str, Any] | None,
    *,
    sponsorship: str | None = None,
    citizenship_required: int | None = None,
    clearance_required: int | None = None,
    work_auth: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Eligibility reconciled from BOTH the deterministic signals and the judge.

    A hard deterministic conflict wins (it is certain); otherwise we defer to the
    judge's enum (or 'unclear' when it has not run). This makes ineligibility
    visible across the whole pool without an LLM per job."""
    det = deterministic_ineligible(
        sponsorship=sponsorship,
        citizenship_required=citizenship_required,
        clearance_required=clearance_required,
        work_auth=work_auth,
    )
    if det is not None:
        return det
    return eligibility(breakdown)


# ── geo eligibility (deterministic India filter) ────────────────────────────────
#
# The user can only work in India (in-country, or remote *from* India). The
# scorer treats location as a soft 10%-weight signal, so a great-fit foreign role
# still bands "strong" -- this hard, no-LLM predicate is what the Today's-roles
# "India-eligible only" filter uses to set those roles aside. By the user's rule a
# remote role qualifies only when India is actually named; a bare
# "Worldwide"/"Anywhere" does not.

# Country-column values (exact, after normalize) that mean India. Adzuna sends the
# ISO-ish "in"; ATS pollers leave the column NULL and fold the country into the
# location string instead, so the text match below carries those.
_INDIA_COUNTRY = {"in", "ind", "india", "bharat"}

# The country word -- word-bounded so "Indiana"/"Indianapolis" never match (the
# 'n'/'a' that follows defeats the boundary). "Indian"/"Indians" do count.
_INDIA_WORD = re.compile(r"\b(?:indian?s?|bharat)\b", re.I)

# Major Indian metros. Matched in the location/remote-scope always, and in the JD
# body too when the country is unknown -- many India roles state the city only in
# the JD ("Location: Bengaluru/Hyderabad/..."). An explicit foreign country blocks
# the JD-body match, so a US role that name-drops a Bangalore office is not pulled
# in. Curated and tunable; a few names are shared with non-India places (e.g.
# Delhi, Ontario) but the filter only *sets a role aside* -- visible, never lost.
_INDIA_CITIES = (
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "hyderabad",
    "pune",
    "chennai",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "cochin",
    "indore",
    "chandigarh",
    "coimbatore",
    "nagpur",
    "mysuru",
    "mysore",
    "trivandrum",
    "thiruvananthapuram",
    "visakhapatnam",
    "vadodara",
    "surat",
    "lucknow",
)
_INDIA_CITY_RE = re.compile(r"\b(?:" + "|".join(_INDIA_CITIES) + r")\b", re.I)


def india_eligible(
    *,
    country: str | None,
    location: str | None,
    remote_scope: str | None,
    jd_text: str | None,
) -> bool:
    """Deterministic 'can this role be worked from India' test. No LLM.

    True when the role is in India or names India (or a major Indian city) as a
    place a candidate may sit. A bare 'Worldwide'/'Anywhere' remote does NOT pass.

    * country in {in, ind, india, bharat}                  -> True
    * 'India'/an Indian city in location or remote_scope   -> True
    * ...or in the JD body, when the country is unknown
      (many India roles state the city only in the JD)     -> True
    * an explicit foreign country blocks the JD-body match, so a role that merely
      name-drops an India office is not pulled in.
    """
    c = (country or "").strip().lower()
    if c in _INDIA_COUNTRY:
        return True
    # An explicit foreign country is authoritative: only the stated location or
    # remote scope can still make it India. Unknown country -> the JD body counts.
    haystack = (
        " ".join(p for p in (location, remote_scope) if p)
        if c
        else " ".join(p for p in (location, remote_scope, jd_text) if p)
    )
    return bool(_INDIA_WORD.search(haystack) or _INDIA_CITY_RE.search(haystack))


# ── freshness ──────────────────────────────────────────────────────────────────


def freshness(
    fresh_col: str | None, closes_at: str | None, today: date | None = None
) -> tuple[str, int | None]:
    """`(freshness, closingInDays)` from the stored columns.

    `closed` column wins (set-aside). Else if `closes_at` is in the future it is
    `closing` with the day count; a past `closes_at` reads `closed`. Otherwise
    `open` (the default until the verify_open job populates these).
    """
    if fresh_col == "closed":
        return "closed", None
    if closes_at:
        d = _parse_date(closes_at)
        if d is not None:
            days = (d - (today or date.today())).days
            if days < 0:
                return "closed", None
            return "closing", days
    if fresh_col == "closing":
        # Marked closing but no parseable deadline — render as closing w/o a count.
        return "closing", None
    return "open", None


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


# ── date helpers (shared shape with tracker.rules) ─────────────────────────────


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def days_since(s: str | None, today: date | None = None) -> int:
    """Whole days since an ISO date/timestamp (>=0). 0 when unknown."""
    d = _parse_date(s)
    if d is None:
        return 0
    delta = ((today or date.today()) - d).days
    return max(delta, 0)


def load_breakdown(score_breakdown_json: str | None) -> dict[str, Any] | None:
    """Parse the stored breakdown JSON, tolerating bad/empty values."""
    if not score_breakdown_json:
        return None
    try:
        val = json.loads(score_breakdown_json)
        return val if isinstance(val, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None
