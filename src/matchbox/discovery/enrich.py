"""Deterministic job-ad enrichment (Tier-2: no LLM, runs on every ingested job).

Pulls the eligibility + seniority signals the SOTA judge needs out of the raw
title/JD with conservative regexes. CONSERVATIVE is the rule: a wrong positive
here (falsely flagging 'no sponsorship', or 'citizens only') would hide a job
the user could actually get -- so every signal defaults to UNKNOWN/None unless
the text is explicit. The LLM never runs at this layer; it only parses
requirements for the jobs the user chooses to pursue.
"""

from __future__ import annotations

import re
from typing import Any

# ── dedup key (mirrors the SQL backfill in migration 007) ─────────────────────


def dedup_key(url: str | None, company: str, title: str, location: str | None = None) -> str:
    """Canonical identity: the url when present, else company|title|location."""
    if url and url.strip():
        return url.strip().lower()
    return f"{company}|{title}|{location or ''}".strip().lower()


# ── seniority (title is the strong signal; checked most-senior first) ─────────

_SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("intern", re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)),
    ("principal", re.compile(r"\b(principal|distinguished|fellow)\b", re.I)),
    ("staff", re.compile(r"\bstaff\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b", re.I)),
    ("lead", re.compile(r"\b(lead|head\s+of)\b", re.I)),
    (
        "junior",
        re.compile(r"\b(junior|jr\.?|entry[- ]level|new[- ]?grad|graduate|associate)\b", re.I),
    ),
]


def parse_seniority(title: str, jd_text: str | None = None) -> str | None:
    """Best-guess seniority from the title. Returns None when nothing explicit
    is present (we do not guess 'mid' -- absence is not evidence)."""
    text = title or ""
    for level, pat in _SENIORITY_PATTERNS:
        if pat.search(text):
            return level
    return None


# ── role family (title is the strong signal; checked most-specific first) ──────

# Ordered so a more specific family wins: "Machine Learning Engineer" is `ml`
# not `backend`; "React Native" is `mobile` not `frontend`; "Full-Stack" beats
# either single side. CONSERVATIVE -- a generic "Software Engineer" stays None
# (we do not guess a specialism the title does not state). This un-deads the
# salary role-scoping, which silently matches zero rows without a family.
_ROLE_FAMILY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ml",
        re.compile(
            r"\b(machine[- ]learning|ml\s*engineer|ai\s*engineer|deep[- ]learning|"
            r"\bnlp\b|computer\s*vision|mlops|research\s*scientist|applied\s*scientist)\b",
            re.I,
        ),
    ),
    (
        "data",
        re.compile(
            r"\b(data\s*engineer|data\s*scientist|data\s*analyst|data\s*science|"
            r"analytics\s*engineer|\banalytics\b|\betl\b|business\s*intelligence)\b",
            re.I,
        ),
    ),
    ("mobile", re.compile(r"\b(ios|android|mobile|react\s*native|flutter|swift|kotlin)\b", re.I)),
    (
        "devops",
        re.compile(
            r"\b(devops|\bsre\b|site\s*reliability|infrastructure|platform\s*engineer|"
            r"cloud\s*engineer)\b",
            re.I,
        ),
    ),
    (
        "security",
        re.compile(
            r"\b(security|appsec|infosec|penetration|cyber\s*security|cybersecurity)\b", re.I
        ),
    ),
    (
        "design",
        re.compile(r"\b(designer|\bux\b|\bui/ux\b|product\s*design|user\s*experience)\b", re.I),
    ),
    (
        "pm",
        re.compile(
            r"\b(product\s*manager|product\s*owner|program\s*manager|technical\s*product)\b", re.I
        ),
    ),
    ("qa", re.compile(r"\b(\bqa\b|quality\s*assurance|test\s*engineer|\bsdet\b)\b", re.I)),
    ("fullstack", re.compile(r"\b(full[- ]?stack)\b", re.I)),
    (
        "frontend",
        re.compile(
            r"\b(frontend|front[- ]end|front\s+end|\breact\b|\bvue\b|\bangular\b|"
            r"ui\s*engineer|web\s*developer)\b",
            re.I,
        ),
    ),
    (
        "backend",
        re.compile(r"\b(backend|back[- ]end|back\s+end|server[- ]side|api\s*engineer)\b", re.I),
    ),
]


def parse_role_family(title: str, jd_text: str | None = None) -> str | None:
    """Best-guess role family from the title, falling back to the JD. Returns
    None when nothing explicit matches (absence is not a guess)."""
    for text in (title or "", jd_text or ""):
        if not text:
            continue
        for family, pat in _ROLE_FAMILY_PATTERNS:
            if pat.search(text):
                return family
    return None


# ── minimum years of experience ───────────────────────────────────────────────

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)


def parse_min_years(jd_text: str | None) -> int | None:
    """The smallest 'N years' mention -- a conservative read of the minimum bar."""
    if not jd_text:
        return None
    nums = [int(m.group(1)) for m in _YEARS.finditer(jd_text)]
    return min(nums) if nums else None


# ── eligibility signals (high precision; unknown unless explicit) ─────────────

_NO_SPONSOR = re.compile(
    r"(no\s+visa\s+sponsorship|without\s+sponsorship|unable\s+to\s+sponsor|"
    r"not?\s+(?:able\s+to\s+)?(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor|"
    r"do(?:es)?\s+not\s+(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor|"
    r"cannot\s+sponsor|are\s+(?:un)?able\s+to\s+sponsor)",
    re.I,
)
_YES_SPONSOR = re.compile(
    r"(visa\s+sponsorship\s+(?:is\s+)?available|sponsorship\s+(?:is\s+)?(?:available|provided|offered)|"
    r"we\s+(?:can\s+|will\s+|do\s+)?sponsor|will\s+sponsor|happy\s+to\s+sponsor)",
    re.I,
)
_CITIZEN = re.compile(
    r"(must\s+be\s+a\s+(?:u\.?s\.?\s+)?citizen|citizens?\s+only|citizenship\s+(?:is\s+)?required|"
    r"u\.?s\.?\s+citizenship\s+required)",
    re.I,
)
_CLEARANCE = re.compile(
    r"(security\s+clearance|secret\s+clearance|ts/sci|top[- ]secret|active\s+clearance)",
    re.I,
)
_REMOTE_SCOPE = re.compile(
    r"remote[^.\n]{0,30}?\b(us|usa|united\s+states|india|emea|eu|europe|uk|canada|apac)\b",
    re.I,
)


def parse_remote_scope(jd_text: str | None) -> str | None:
    """The region a remote role is restricted to, when stated near 'remote'."""
    m = _REMOTE_SCOPE.search(jd_text or "")
    return m.group(1).lower().replace("  ", " ") if m else None


def parse_eligibility(jd_text: str | None) -> dict[str, Any]:
    """{sponsorship, citizenship_required, clearance_required, remote_scope}.

    sponsorship is 'none'/'offered'/'unknown'; the two *_required flags are 1
    when explicit, else None (unknown) -- never 0, because absence of the phrase
    is not proof the bar does not exist."""
    t = jd_text or ""
    if _NO_SPONSOR.search(t):
        sponsorship = "none"
    elif _YES_SPONSOR.search(t):
        sponsorship = "offered"
    else:
        sponsorship = "unknown"
    return {
        "sponsorship": sponsorship,
        "citizenship_required": 1 if _CITIZEN.search(t) else None,
        "clearance_required": 1 if _CLEARANCE.search(t) else None,
        "remote_scope": parse_remote_scope(t),
    }


def enrich_record(title: str, jd_text: str | None) -> dict[str, Any]:
    """All Tier-2 signals for one job, ready to write onto its columns."""
    return {
        "seniority": parse_seniority(title, jd_text),
        "min_years_exp": parse_min_years(jd_text),
        "role_family": parse_role_family(title, jd_text),
        **parse_eligibility(jd_text),
    }
