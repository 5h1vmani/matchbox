"""Deterministic 5-dimension scoring rubric. Section 11 of v0.3-design.md.

Every dimension is computed from real data the user has provided
(`target` row, library tags, exclusions). The score is a weighted sum;
the breakdown is returned so the UI can show *why*.

No hardcoded constants. v0.2's `comp_score` and `cultural_score` are
dropped because they could not be computed honestly from a JD alone.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from matchbox.core.text import tokenize as _tokens_list

RUBRIC_PATH = Path(__file__).resolve().parents[3] / "shared" / "rubric.json"

REMOTE_TOKENS = {"remote", "anywhere", "distributed", "work-from-home", "wfh"}


@dataclass(slots=True)
class DimensionScore:
    name: str
    score: float
    weight: float
    reason: str


@dataclass(slots=True)
class JobScore:
    total: float
    dimensions: list[DimensionScore] = field(default_factory=list)

    def to_breakdown_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 4),
                    "weight": d.weight,
                    "reason": d.reason,
                }
                for d in self.dimensions
            ],
        }


def load_rubric() -> dict[str, Any]:
    """Read the rubric JSON. Cached at module load."""
    data: dict[str, Any] = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    return data


_RUBRIC = load_rubric()


def _weights() -> dict[str, float]:
    return {name: d["default_weight"] for name, d in _RUBRIC["dimensions"].items()}


# ─── tokenization ─────────────────────────────────────────────────────
#
# Shared with matching/bm25.py via core/text.py so the two cannot drift.
# We work in sets here because rubric scoring is overlap-based, not
# ranked retrieval.


def _tokens(text: str) -> set[str]:
    return set(_tokens_list(text))


# ─── per-dimension scorers ────────────────────────────────────────────


def _role_title_score(job_title: str, role_families: list[str]) -> DimensionScore:
    weight = _weights()["role_title"]
    if not role_families:
        return DimensionScore(
            name="role_title",
            score=0.5,
            weight=weight,
            reason="no target role_families set (neutral)",
        )
    title_tokens = _tokens(job_title)
    best_overlap = 0.0
    best_family = ""
    for fam in role_families:
        fam_tokens = _tokens(fam)
        if not fam_tokens:
            continue
        overlap = len(title_tokens & fam_tokens) / len(fam_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_family = fam
    return DimensionScore(
        name="role_title",
        score=min(best_overlap, 1.0),
        weight=weight,
        reason=(
            f"matched {best_overlap:.0%} of '{best_family}'"
            if best_family
            else "no overlap with target role_families"
        ),
    )


def _skills_overlap_score(jd_text: str, user_tech_tokens: set[str]) -> DimensionScore:
    weight = _weights()["skills_overlap"]
    if not user_tech_tokens:
        return DimensionScore(
            name="skills_overlap",
            score=0.5,
            weight=weight,
            reason="no library skills/tech yet (neutral)",
        )
    jd_tokens = _tokens(jd_text)
    hits = sorted(user_tech_tokens & jd_tokens)
    score = min(len(hits) / max(3, min(len(user_tech_tokens), 8)), 1.0)
    if not hits:
        return DimensionScore(
            name="skills_overlap",
            score=0.0,
            weight=weight,
            reason="no library skills appear in JD",
        )
    listed = ", ".join(hits[:5]) + ("…" if len(hits) > 5 else "")
    return DimensionScore(
        name="skills_overlap",
        score=score,
        weight=weight,
        reason=f"{len(hits)} skill hit{'s' if len(hits) != 1 else ''}: {listed}",
    )


def _company_tier_score(company: str, dreams: list[str], exclusions: list[str]) -> DimensionScore:
    weight = _weights()["company_tier"]
    company_l = company.lower().strip()
    excl_l = [e.lower().strip() for e in exclusions]
    dream_l = [d.lower().strip() for d in dreams]

    if any(e and e in company_l for e in excl_l):
        return DimensionScore(
            name="company_tier",
            score=0.0,
            weight=weight,
            reason=f"excluded: '{company}' matches an exclusion term",
        )
    if any(d == company_l for d in dream_l):
        return DimensionScore(
            name="company_tier", score=1.0, weight=weight, reason=f"dream company: {company}"
        )
    return DimensionScore(
        name="company_tier",
        score=0.5,
        weight=weight,
        reason="neither dream nor excluded (neutral)",
    )


def _location_remote_score(job_location: str | None, target_locations: list[str]) -> DimensionScore:
    weight = _weights()["location_remote"]
    if not job_location:
        return DimensionScore(
            name="location_remote",
            score=0.5,
            weight=weight,
            reason="JD location unknown (neutral)",
        )
    job_l = job_location.lower()
    targets_l = [t.lower().strip() for t in target_locations]

    if any(t in REMOTE_TOKENS for t in targets_l) and any(tok in job_l for tok in REMOTE_TOKENS):
        return DimensionScore(
            name="location_remote",
            score=1.0,
            weight=weight,
            reason=f"remote target met: '{job_location}'",
        )

    if not targets_l:
        return DimensionScore(
            name="location_remote",
            score=0.5,
            weight=weight,
            reason="no target locations set (neutral)",
        )

    for t in targets_l:
        if t and t in job_l:
            return DimensionScore(
                name="location_remote",
                score=1.0,
                weight=weight,
                reason=f"matches target '{t}'",
            )

    return DimensionScore(
        name="location_remote",
        score=0.2,
        weight=weight,
        reason=f"'{job_location}' not in target locations",
    )


def _red_flags_score(
    jd_text: str, job_title: str, company: str, exclusions: list[str]
) -> DimensionScore:
    """Inverse: 1.0 means clean, lower means a flag tripped."""
    weight = _weights()["red_flags"]
    if not exclusions:
        return DimensionScore(
            name="red_flags",
            score=1.0,
            weight=weight,
            reason="no exclusions configured",
        )
    haystack = f"{jd_text} {job_title} {company}".lower()
    tripped: list[str] = []
    for term in exclusions:
        if term and term.lower().strip() in haystack:
            tripped.append(term)
    if not tripped:
        return DimensionScore(
            name="red_flags", score=1.0, weight=weight, reason="no exclusion terms found"
        )
    return DimensionScore(
        name="red_flags",
        score=0.0,
        weight=weight,
        reason=f"hit exclusion(s): {', '.join(tripped)}",
    )


# ─── orchestration ────────────────────────────────────────────────────


def _user_tech_tokens(conn: sqlite3.Connection) -> set[str]:
    """Collect every tech token from the user's library — skill names and
    `tech`-facet tag values, lowercased.
    """
    tokens: set[str] = set()
    for row in conn.execute("SELECT name FROM skill"):
        tokens.update(_tokens(row[0]))
    for row in conn.execute("SELECT value FROM tag WHERE facet = 'tech'"):
        tokens.update(_tokens(row[0]))
    return tokens


def _load_target(conn: sqlite3.Connection) -> dict[str, list[str]]:
    row = conn.execute("SELECT * FROM target LIMIT 1").fetchone()
    if row is None:
        return {"role_families": [], "dream_companies": [], "locations": [], "exclusions": []}
    return {
        "role_families": json.loads(row["role_families_json"]),
        "dream_companies": json.loads(row["dream_companies_json"]),
        "locations": json.loads(row["locations_json"]),
        "exclusions": json.loads(row["exclusions_json"]),
    }


def score_job(
    *,
    job: dict[str, Any],
    target: dict[str, list[str]],
    user_tech_tokens: set[str],
) -> JobScore:
    """Score one job. Pure function. No DB writes."""
    dimensions = [
        _role_title_score(job["title"], target["role_families"]),
        _skills_overlap_score(job["jd_text"] or "", user_tech_tokens),
        _company_tier_score(job["company"], target["dream_companies"], target["exclusions"]),
        _location_remote_score(job.get("location"), target["locations"]),
        _red_flags_score(job["jd_text"] or "", job["title"], job["company"], target["exclusions"]),
    ]
    total = sum(d.score * d.weight for d in dimensions)
    return JobScore(total=total, dimensions=dimensions)


def score_all_new(conn: sqlite3.Connection) -> int:
    """Score every job with status='new'. Flip status to 'scored'. Returns count."""
    target = _load_target(conn)
    tokens = _user_tech_tokens(conn)
    rows = conn.execute(
        "SELECT id, company, title, location, jd_text FROM job WHERE status = 'new'"
    ).fetchall()
    n = 0
    for r in rows:
        job = dict(r)
        result = score_job(job=job, target=target, user_tech_tokens=tokens)
        conn.execute(
            """
            UPDATE job SET score = ?, score_breakdown_json = ?, status = 'scored'
             WHERE id = ?
            """,
            (result.total, json.dumps(result.to_breakdown_dict()), job["id"]),
        )
        n += 1
    return n


def rescore_all(conn: sqlite3.Connection) -> int:
    """Recompute scores for every job that has not been tailored/applied yet.
    Status moves to 'scored'; any 'new' rows also get a score in the same pass.
    Tailored/applied jobs are intentionally left alone."""
    target = _load_target(conn)
    tokens = _user_tech_tokens(conn)
    rows = conn.execute(
        """
        SELECT id, company, title, location, jd_text
          FROM job
         WHERE status IN ('new', 'scored', 'selected', 'rejected', 'skipped')
        """
    ).fetchall()
    n = 0
    for r in rows:
        job = dict(r)
        result = score_job(job=job, target=target, user_tech_tokens=tokens)
        conn.execute(
            """
            UPDATE job
               SET score = ?, score_breakdown_json = ?,
                   status = CASE WHEN status = 'new' THEN 'scored' ELSE status END
             WHERE id = ?
            """,
            (result.total, json.dumps(result.to_breakdown_dict()), job["id"]),
        )
        n += 1
    return n
