"""Component selection: embed → score → fuse → MMR → coverage.

The orchestrator for matching. Inputs: components (bullets), requirements
(parsed from the JD by the brain). Output: selected component ids in the
order MMR picked them, plus a coverage matrix.

Selection is deterministic. Same inputs always yield the same outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from matchbox.matching.bm25 import BM25Index
from matchbox.matching.embed import cosine_matrix
from matchbox.matching.mmr import mmr_select
from matchbox.matching.rrf import rrf_fuse

SEMANTIC_COVERAGE_FLOOR = 0.35
TOP_PER_REQUIREMENT = 8

# One-page budget heuristic. Approximates ~450 words of body across all
# selected bullets, leaving room for profile, summary, skills, headings.
# Bullets are 8 to 25 words per voice-rules.json; 450 / 15 ≈ 30 bullets
# max, but the per-role cap × number of roles bounds it well below that
# in practice. The budget is the final safety belt.
DEFAULT_WORD_BUDGET = 450

# Recency decay (years from end_date to "now"): exp(-years / TAU).
# TAU = 4 means a 4-year-old role keeps ≈ 0.37 weight, an 8-year-old
# role ≈ 0.14. Currently-employed bullets (end_date = None or "present")
# get full weight (1.0).
RECENCY_TAU_YEARS = 4.0
HAS_METRIC_BOOST = 0.15

_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?")


@dataclass(slots=True)
class Component:
    id: int
    text: str
    experience_id: int  # for the per-role cap
    has_metric: bool = False
    # `end_date` is read off the parent experience by the loader. None or
    # "present" means current. Used for the recency prior.
    end_date: str | None = None


def _years_since(end_date: str | None, now: datetime | None = None) -> float:
    """Years between `end_date` and now. None or "present" returns 0.0."""
    if not end_date or end_date.strip().lower() == "present":
        return 0.0
    m = _DATE_RE.match(end_date.strip())
    if m is None:
        return 0.0
    year = int(m.group(1))
    month = int(m.group(2) or 1)
    day = int(m.group(3) or 1)
    try:
        end = datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return 0.0
    today = now or datetime.now(UTC)
    return max(0.0, (today - end).days / 365.25)


def _recency_weight(end_date: str | None, now: datetime | None = None) -> float:
    """exp(-years_since / TAU). Bounded to [0.05, 1.0] so very old roles
    still surface if they uniquely cover a must-have."""
    years = _years_since(end_date, now=now)
    return float(max(0.05, np.exp(-years / RECENCY_TAU_YEARS)))


def _word_count(text: str) -> int:
    return len(text.split())


def _budget_trim(
    *,
    selected_ids: list[int],
    components_by_id: dict[int, Component],
    relevance: dict[int, float],
    word_budget: int,
) -> list[int]:
    """Drop trailing bullets (by ascending relevance) until total body
    word count is within budget. Preserves MMR order of the survivors."""
    if word_budget <= 0:
        return selected_ids
    order = list(selected_ids)
    used = sum(_word_count(components_by_id[i].text) for i in order)
    if used <= word_budget:
        return order
    # Sort the *candidates to drop* by ascending relevance — drop the
    # weakest first. Keep dropping until we are within budget.
    ranked_to_drop = sorted(order, key=lambda i: relevance.get(i, 0.0))
    keep = set(order)
    for cid in ranked_to_drop:
        if used <= word_budget:
            break
        if cid in keep:
            keep.remove(cid)
            used -= _word_count(components_by_id[cid].text)
    return [cid for cid in order if cid in keep]


@dataclass(slots=True)
class Requirement:
    text: str
    type: str  # must-have | responsibility | nice
    keywords: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SelectionResult:
    selected_ids: list[int]
    relevance_by_component: dict[int, float]
    similarity_matrix: np.ndarray  # shape: (components, requirements)
    covered: list[bool]  # one bool per must-have requirement


def _query_for_requirement(r: Requirement) -> str:
    """Concatenate the requirement text and any keywords/variants — gives
    BM25 a richer query."""
    parts = [r.text, *r.keywords, *r.variants]
    return " ".join(p for p in parts if p)


def select_components(
    *,
    components: list[Component],
    component_embeddings: list[np.ndarray],
    requirements: list[Requirement],
    requirement_embeddings: list[np.ndarray],
    k: int,
    per_role_cap: int = 4,
    lam: float = 0.5,
    coverage_floor: float = SEMANTIC_COVERAGE_FLOOR,
    word_budget: int = DEFAULT_WORD_BUDGET,
    now: datetime | None = None,
) -> SelectionResult:
    """Run the full pipeline. The caller owns embedding generation."""
    if not components:
        return SelectionResult(
            selected_ids=[],
            relevance_by_component={},
            similarity_matrix=np.zeros((0, len(requirements)), dtype=np.float32),
            covered=[False] * sum(1 for r in requirements if r.type == "must-have"),
        )

    # Dense similarity: components × requirements
    sim = (
        cosine_matrix(component_embeddings, requirement_embeddings)
        if requirements
        else np.zeros((len(components), 0), dtype=np.float32)
    )

    # Sparse rankings: per requirement, rank components by BM25 score
    bm25 = BM25Index([c.text for c in components])
    sparse_rankings_by_req: list[list[int]] = []
    for r in requirements:
        scores = bm25.score(_query_for_requirement(r))
        order = sorted(
            range(len(components)),
            key=lambda i: (scores[i] if i < len(scores) else 0.0),
            reverse=True,
        )
        sparse_rankings_by_req.append(order)

    # Dense rankings: per requirement, rank components by cosine
    dense_rankings_by_req: list[list[int]] = []
    for j in range(len(requirements)):
        col = sim[:, j] if sim.size else np.zeros(len(components))
        order = sorted(range(len(components)), key=lambda i: float(col[i]), reverse=True)
        dense_rankings_by_req.append(order)

    # Per-requirement fused candidates (component indices, fused score)
    fused_by_req: list[list[tuple[int, float]]] = []
    for dense_rank, sparse_rank in zip(dense_rankings_by_req, sparse_rankings_by_req, strict=True):
        fused_by_req.append(rrf_fuse([dense_rank, sparse_rank]))

    # Per-component relevance = max fused score across all must-have requirements;
    # falls back to all requirements if none are must-have.
    must_have_idx = [i for i, r in enumerate(requirements) if r.type == "must-have"]
    target_indices = must_have_idx if must_have_idx else list(range(len(requirements)))

    # Priors: × has_metric boost × recency weight. Recency is per-component
    # because every bullet inherits its experience's end_date.
    metric_prior = {c.id: 1.0 + (HAS_METRIC_BOOST if c.has_metric else 0.0) for c in components}
    recency_prior = {c.id: _recency_weight(c.end_date, now=now) for c in components}

    relevance_by_component: dict[int, float] = {c.id: 0.0 for c in components}
    for j in target_indices:
        topN = fused_by_req[j][:TOP_PER_REQUIREMENT]
        for comp_idx, fused_score in topN:
            comp = components[comp_idx]
            prior = metric_prior[comp.id] * recency_prior[comp.id]
            relevance_by_component[comp.id] = max(
                relevance_by_component[comp.id], fused_score * prior
            )

    # MMR using component embeddings keyed by component.id
    emb_by_id = {c.id: e for c, e in zip(components, component_embeddings, strict=True)}
    group_of = {c.id: c.experience_id for c in components}

    selected = mmr_select(
        candidate_ids=[c.id for c in components],
        embeddings=emb_by_id,
        relevance=lambda cid: relevance_by_component.get(cid, 0.0),
        k=k,
        lam=lam,
        per_group_cap=per_role_cap,
        group_of=lambda cid: group_of[cid],
    )

    # One-page budget: drop trailing low-relevance bullets until total
    # word count fits.
    components_by_id = {c.id: c for c in components}
    selected = _budget_trim(
        selected_ids=selected,
        components_by_id=components_by_id,
        relevance=relevance_by_component,
        word_budget=word_budget,
    )

    # Coverage on must-haves
    covered: list[bool] = []
    selected_idx = {c.id: i for i, c in enumerate(components) if c.id in set(selected)}
    for j, r in enumerate(requirements):
        if r.type != "must-have":
            continue
        best = 0.0
        for cid in selected:
            i = selected_idx[cid]
            if sim.size:
                best = max(best, float(sim[i, j]))
        covered.append(best >= coverage_floor)

    return SelectionResult(
        selected_ids=selected,
        relevance_by_component=relevance_by_component,
        similarity_matrix=sim,
        covered=covered,
    )
