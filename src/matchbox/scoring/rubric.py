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

import numpy as np

from matchbox.core.text import tokenize as _tokens_list
from matchbox.matching.embed import Embedder, cached_encode, cosine

RUBRIC_PATH = Path(__file__).resolve().parents[3] / "shared" / "rubric.json"

REMOTE_TOKENS = {"remote", "anywhere", "distributed", "work-from-home", "wfh"}

# Filler tokens that must never count as a skill hit. The shared tokenizer
# does not strip stopwords, so multi-word skill names ("Directing AI coding
# agents") would otherwise leak "and"/"to" into the skill set.
_STOPWORDS = {
    "a",
    "an",
    "as",
    "at",
    "by",
    "in",
    "of",
    "on",
    "or",
    "to",
    "is",
    "it",
    "and",
    "the",
    "for",
    "with",
    "you",
    "your",
    "our",
    "are",
    "from",
    "this",
    "that",
    "into",
    "per",
    "via",
    "use",
    "using",
    "etc",
    "we",
    "be",
    "all",
}

# Role words too generic to imply a title match on their own (a lone
# "engineer" must not make a coding-IC role look like an AI-role fit).
_GENERIC_ROLE_WORDS = {
    "engineer",
    "engineering",
    "developer",
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "specialist",
    "associate",
    "of",
    "and",
    "the",
    "sr",
    "jr",
}


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
_SKILLS_TARGET_HITS = max(1, int(_RUBRIC.get("skills_target_hits", 5)))


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
        # Match on the family's *meaningful* tokens only; a shared generic
        # word like "engineer" must not produce a title match by itself.
        fam_meaningful = _tokens(fam) - _GENERIC_ROLE_WORDS
        if not fam_meaningful:
            continue
        overlap = len(title_tokens & fam_meaningful) / len(fam_meaningful)
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
            else "no meaningful overlap with target role_families"
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
    # Drop stopwords and 1-2 char tokens so filler pulled out of multi-word
    # skill names ("and", "as", "to") cannot count as a skill hit.
    hits = sorted(t for t in (user_tech_tokens & jd_tokens) if len(t) > 2 and t not in _STOPWORDS)
    # Explicit-skill recall, normalized by a tunable target hit count.
    # (Replaces the old max(3, min(n, 8)) denominator, which silently
    # capped users with few skills below 1.0.)
    score = min(len(hits) / _SKILLS_TARGET_HITS, 1.0)
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


def _semantic_fit_score(cosine_sim: float) -> DimensionScore:
    """Dense-embedding fit: cosine(profile centroid, JD embedding).

    Computed locally with bge-small, zero tokens. Clamped to [0, 1]; the
    absolute meaning of the number comes from the batch calibration in
    `calibrate_bands`, not from the raw cosine.
    """
    weight = _weights().get("semantic_fit", 0.35)
    return DimensionScore(
        name="semantic_fit",
        score=max(0.0, min(cosine_sim, 1.0)),
        weight=weight,
        reason=f"profile-JD embedding similarity {cosine_sim:.2f}",
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
    semantic_fit: float | None = None,
) -> JobScore:
    """Score one job. Pure function. No DB writes.

    `semantic_fit` is the precomputed cosine between the profile centroid
    and the JD embedding (see `score_all_new`). When None (no embedder,
    e.g. unit tests), the dimension is omitted and the remaining weights
    are renormalized so the total still lands in [0, 1].
    """
    dimensions: list[DimensionScore] = []
    if semantic_fit is not None:
        dimensions.append(_semantic_fit_score(semantic_fit))
    dimensions.extend(
        [
            _role_title_score(job["title"], target["role_families"]),
            _skills_overlap_score(job["jd_text"] or "", user_tech_tokens),
            _company_tier_score(job["company"], target["dream_companies"], target["exclusions"]),
            _location_remote_score(job.get("location"), target["locations"]),
            _red_flags_score(
                job["jd_text"] or "", job["title"], job["company"], target["exclusions"]
            ),
        ]
    )
    weight_sum = sum(d.weight for d in dimensions)
    total = sum(d.score * d.weight for d in dimensions) / weight_sum if weight_sum else 0.0
    return JobScore(total=total, dimensions=dimensions)


def _profile_centroid(conn: sqlite3.Connection, embedder: Embedder) -> np.ndarray | None:
    """Mean of the L2-normalized embeddings of the user's bullets and
    skills. The single vector that represents "who this candidate is",
    compared against each JD embedding for the semantic_fit signal."""
    items: list[tuple[str, int, str]] = []
    for r in conn.execute("SELECT id, text FROM bullet"):
        items.append(("bullet", int(r["id"]), str(r["text"])))
    for r in conn.execute("SELECT id, name FROM skill"):
        items.append(("skill", int(r["id"]), str(r["name"])))
    if not items:
        return None
    vecs = cached_encode(conn, embedder, items)
    normed = [v / max(float(np.linalg.norm(v)), 1e-12) for v in vecs.values()]
    if not normed:
        return None
    centroid: np.ndarray = np.vstack(normed).mean(axis=0)
    return centroid


def calibrate_bands(totals: list[float]) -> list[str]:
    """Map raw totals to interpretable bands. Percentile-based across the
    batch (adaptive to the user's market) when there are enough jobs;
    fixed thresholds otherwise. No labels required."""
    cfg = _RUBRIC.get("calibration", {})
    bands: list[str] = cfg.get("bands", ["skip", "weak", "stretch", "strong"])
    if not totals:
        return []
    if len(totals) >= 5:
        cutoffs = [
            float(q)
            for q in np.quantile(np.array(totals), cfg.get("quantile_cutoffs", [0.4, 0.7, 0.9]))
        ]
    else:
        cutoffs = [0.3, 0.5, 0.7]
    return [bands[min(sum(1 for c in cutoffs if t >= c), len(bands) - 1)] for t in totals]


def _compute_and_store(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    embedder: Embedder | None,
    *,
    status_clause: str,
) -> int:
    target = _load_target(conn)
    tokens = _user_tech_tokens(conn)
    centroid = _profile_centroid(conn, embedder) if embedder is not None else None

    scored: list[tuple[int, JobScore]] = []
    for r in rows:
        job = dict(r)
        semantic_fit: float | None = None
        if embedder is not None and centroid is not None and job.get("jd_text"):
            jd_vec = embedder.encode([job["jd_text"]])[0]
            semantic_fit = cosine(centroid, jd_vec)
        scored.append(
            (
                int(job["id"]),
                score_job(
                    job=job, target=target, user_tech_tokens=tokens, semantic_fit=semantic_fit
                ),
            )
        )

    bands = calibrate_bands([s.total for _, s in scored])
    for (jid, result), band in zip(scored, bands, strict=True):
        breakdown = result.to_breakdown_dict()
        breakdown["band"] = band
        conn.execute(
            f"UPDATE job SET score = ?, score_breakdown_json = ?, status = {status_clause} WHERE id = ?",
            (result.total, json.dumps(breakdown), jid),
        )
    return len(scored)


def score_all_new(conn: sqlite3.Connection, embedder: Embedder | None = None) -> int:
    """Score every job with status='new'; flip status to 'scored'. Returns count.

    Pass an `embedder` to enable the semantic_fit dimension (the web app
    does; unit tests omit it to stay off the model download path)."""
    rows = conn.execute(
        "SELECT id, company, title, location, jd_text FROM job WHERE status = 'new'"
    ).fetchall()
    return _compute_and_store(conn, rows, embedder, status_clause="'scored'")


def rescore_all(conn: sqlite3.Connection, embedder: Embedder | None = None) -> int:
    """Recompute scores for every job not yet tailored/applied. 'new' rows
    move to 'scored'; tailored/applied jobs are left alone."""
    rows = conn.execute(
        """
        SELECT id, company, title, location, jd_text
          FROM job
         WHERE status IN ('new', 'scored', 'selected', 'rejected', 'skipped')
        """
    ).fetchall()
    return _compute_and_store(
        conn, rows, embedder, status_clause="CASE WHEN status = 'new' THEN 'scored' ELSE status END"
    )
