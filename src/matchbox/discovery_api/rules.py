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


def jd_paragraphs(jd_text: str | None) -> list[str]:
    """Split a JD blob into display paragraphs (blank-line separated; falls back
    to single newlines; never empty when there is any text)."""
    if not jd_text or not jd_text.strip():
        return []
    text = jd_text.replace("\r\n", "\n").strip()
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
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
