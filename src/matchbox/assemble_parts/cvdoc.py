"""CV-document assembly: free-text date parsing, reverse-chronological
experience ordering, education/degree routing, cv.json construction, and the
default summary pick. Extracted from assemble.py."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, cast

from matchbox.core.text import METRIC_UNIT_WORDS
from matchbox.matching.select import Component

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}

# A role that names a degree -> the row is education, not work. Disambiguates the
# common case where one institution holds both a degree and a job (e.g. an MSc and
# a Research Assistant role at the same university): the ROLE decides, not the
# employer. Deliberately strict so job titles like "Senior Associate" do not match.
_DEGREE_RE = re.compile(
    r"(?i)\b("
    r"bachelor|master|doctor(?:ate)?|ph\.?d|mba|"
    r"b\.?(?:sc|com|tech|a|e|ed|arch)|m\.?(?:sc|com|tech|a|e|ed|arch|phil)|"
    r"ll\.?[bm]|diploma|associate of (?:arts|science)"
    r")\b"
)


def _is_degree_role(role: str | None) -> bool:
    return bool(_DEGREE_RE.search(role or ""))


def _exp_date_key(date_str: str | None) -> tuple[int, int]:
    """Sortable (year, month) from an experience date in either format the DB
    holds: free-text ("Aug 2025", bare "2014") or ISO ("2024-08-01", "2024-08").

    "present"/"" -> (9999, 13) so an ongoing role sorts newest. "Aug 2025" ->
    (2025, 8); "2024-08-01" -> (2024, 8); a bare "2014" -> (2014, 0). Unparsable
    text sinks to (0, 0) rather than corrupting the order.
    """
    s = (date_str or "").strip().lower()
    if not s or s == "present":
        return (9999, 13)
    iso = re.match(r"(\d{4})-(\d{2})", s)
    if iso:
        return (int(iso.group(1)), int(iso.group(2)))
    month = 0
    year = 0
    for tok in s.replace(",", " ").split():
        if tok[:3] in _MONTHS:
            month = _MONTHS[tok[:3]]
        elif tok.isdigit() and len(tok) == 4:
            year = int(tok)
    return (year, month)


def _experiences_in_order(
    components: list[Component], raw_bullets: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group selected components into experiences, ordered reverse-chronologically
    and grouped by employer.

    Reverse-chronological (newest first, "present" on top) is the CV standard:
    ATS parsers map the first dated block as the current role, and recruiters scan
    top-down expecting recency. Grouping by employer keeps a company's roles
    adjacent and newest-first, so a promotion reads as progression instead of
    scattering across the page. Bullet order within a role is left as the brain
    chose it (impact-first).
    """
    by_exp: dict[int, dict[str, Any]] = {}
    for c in components:
        b = raw_bullets[c.id]
        ex_id = c.experience_id
        if ex_id not in by_exp:
            by_exp[ex_id] = {
                "_exp_id": ex_id,
                "company": b["company"],
                "role": b["role"],
                "start_date": b["start_date"] or "",
                "end_date": b["end_date"] or "present",
                "location": b["location"],
                "bullets": [],
            }
        cast(list[str], by_exp[ex_id]["bullets"]).append(b["text"])

    rows = list(by_exp.values())
    role_key = {
        x["_exp_id"]: (_exp_date_key(x["end_date"]), _exp_date_key(x["start_date"])) for x in rows
    }
    # Each company sorts by its most-recent role, so every role at one employer
    # stays together (newest first) rather than scattering between other companies.
    company_key: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    for x in rows:
        company_key[x["company"]] = max(
            company_key.get(x["company"], ((0, 0), (0, 0))), role_key[x["_exp_id"]]
        )
    ordered = sorted(
        rows,
        key=lambda x: (company_key[x["company"]], role_key[x["_exp_id"]]),
        reverse=True,
    )
    for ex in ordered:
        ex.pop("_exp_id", None)
    return ordered


_SKILLS_MAX_CATS = 4
_SKILLS_MAX_ITEMS = 18
_SKILLS_MIN_MATCH = 6
_SKILLS_FALLBACK_CAP = 12

# Unit/scale words whose presence after a number makes it a metric.
_UNIT_WORDS = METRIC_UNIT_WORDS


def _jd_matched_skills(conn: sqlite3.Connection, jd_text: str) -> tuple[list[dict[str, Any]], str]:
    """Filter skills by JD relevance; never dump the library.

    Returns (skill_groups, summary_line) where summary_line describes what
    happened for changes.md (e.g. "Skills: 12 of 54 rendered (JD-matched)").
    """
    all_rows = conn.execute(
        "SELECT id, category, name FROM skill ORDER BY category, name"
    ).fetchall()
    total = len(all_rows)
    if total == 0:
        return [], "Skills: 0 of 0 rendered (no library skills)"

    jd_lower = jd_text.lower()

    # Word-boundary-aware check: split name into tokens; require all tokens to
    # appear in the JD (handles "React Native" matching "react native" in JD).
    def _matches(name: str) -> bool:
        tokens = re.split(r"[\s/\-]+", name.lower())
        return all(tok in jd_lower for tok in tokens if tok)

    matched = [r for r in all_rows if _matches(r["name"])]
    used_ids = {r["id"] for r in matched}

    # Top-up to _SKILLS_MIN_MATCH if too few matched.
    if len(matched) < _SKILLS_MIN_MATCH:
        topup_candidates = [r for r in all_rows if r["id"] not in used_ids]
        topup = topup_candidates[: _SKILLS_FALLBACK_CAP - len(matched)]
        matched = matched + topup

    # Cap to _SKILLS_MAX_ITEMS items and _SKILLS_MAX_CATS categories, dropping
    # whole lowest-yield categories beyond the cap.
    cat_buckets: dict[str, list[str]] = {}
    cat_order: list[str] = []
    for r in matched:
        cat = r["category"] or "Other"
        if cat not in cat_buckets:
            cat_order.append(cat)
            cat_buckets[cat] = []
        cat_buckets[cat].append(r["name"])

    # Drop categories beyond _SKILLS_MAX_CATS (by ascending yield — drop smallest).
    if len(cat_order) > _SKILLS_MAX_CATS:
        # Sort by descending yield; keep top _SKILLS_MAX_CATS.
        cat_order_sorted = sorted(cat_order, key=lambda c: len(cat_buckets[c]), reverse=True)
        kept_cats = set(cat_order_sorted[:_SKILLS_MAX_CATS])
        cat_order = [c for c in cat_order if c in kept_cats]

    # Trim total items to _SKILLS_MAX_ITEMS across all kept categories.
    skills: list[dict[str, Any]] = []
    remaining = _SKILLS_MAX_ITEMS
    for cat in cat_order:
        items = cat_buckets[cat][:remaining]
        if items:
            skills.append({"category": cat, "items": items})
            remaining -= len(items)
        if remaining <= 0:
            break

    rendered_count = sum(len(g["items"]) for g in skills)
    summary_line = f"Skills: {rendered_count} of {total} rendered (JD-matched)"
    return skills, summary_line


def _build_cv_json(
    *,
    profile: dict[str, Any],
    experiences: list[dict[str, Any]],
    summary_text: str,
    conn: sqlite3.Connection,
    projects: list[dict[str, Any]] | None = None,
    selected_skills: list[dict[str, Any]] | None = None,
    jd_text: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Build the cv.json dict.

    Returns (cv_dict, skills_summary_line) where skills_summary_line is
    suitable for appending to changes.md.
    """
    if selected_skills is not None:
        # Brain explicitly chose skills.
        skills = selected_skills
        total = conn.execute("SELECT COUNT(*) FROM skill").fetchone()[0]
        rendered_count = sum(len(g["items"]) for g in skills)
        skills_summary_line = f"Skills: {rendered_count} of {total} rendered (brain-selected)"
    elif jd_text:
        skills, skills_summary_line = _jd_matched_skills(conn, jd_text)
    else:
        # Last-resort fallback: dump full library (pre-existing behaviour for
        # callers that do not pass jd_text).
        all_rows = conn.execute(
            "SELECT category, name FROM skill ORDER BY category, name"
        ).fetchall()
        skill_by_cat: dict[str, list[str]] = {}
        for r in all_rows:
            cat = r["category"] or "Other"
            skill_by_cat.setdefault(cat, []).append(r["name"])
        skills = [{"category": cat, "items": items} for cat, items in skill_by_cat.items()]
        total = sum(len(g["items"]) for g in skills)
        skills_summary_line = f"Skills: {total} of {total} rendered (full library)"

    contact: list[str] = []
    if profile.get("email"):
        contact.append(str(profile["email"]))
    if profile.get("phone"):
        contact.append(str(profile["phone"]))
    if profile.get("location"):
        contact.append(str(profile["location"]))
    links = json.loads(str(profile.get("links_json") or "[]"))
    contact.extend(links)

    # Education: degrees live in the `experience` table, so route the degree-roles
    # into their own section (newest first). Shown on every CV regardless of
    # bullet selection -- credentials are not bullets. Work experiences drop any
    # degree-role for the same reason, so a degree never renders as a job.
    work = [e for e in experiences if not _is_degree_role(e.get("role"))]
    degree_rows = [
        r
        for r in conn.execute(
            "SELECT company, role, start_date, end_date FROM experience"
        ).fetchall()
        if _is_degree_role(r["role"])
    ]
    degree_rows.sort(
        key=lambda r: (_exp_date_key(r["end_date"]), _exp_date_key(r["start_date"])),
        reverse=True,
    )
    education = [
        {
            "degree": r["role"],
            "school": r["company"],
            "dates": " to ".join(d for d in (r["start_date"], r["end_date"]) if d)
            or (r["end_date"] or ""),
        }
        for r in degree_rows
    ]

    cv_dict = {
        "schema_version": 1,
        "profile": {
            "name": str(profile.get("full_name", "Your Name")),
            "headline": str(profile.get("headline") or ""),
            "contact": contact,
        },
        "summary": summary_text,
        "experiences": work,
        "projects": projects or [],
        "skills": skills,
        "education": education,
    }
    return cv_dict, skills_summary_line


def _pick_summary(conn: sqlite3.Connection) -> str:
    """The brain may eventually pick a tagged summary_variant; for v1
    we use the most recently added one, if any."""
    row = conn.execute("SELECT text FROM summary_variant ORDER BY id DESC LIMIT 1").fetchone()
    return str(row[0]) if row else ""
