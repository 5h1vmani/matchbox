"""Component selection: embed → score → fuse → MMR → coverage.

The orchestrator for matching. Inputs: components (bullets), requirements
(parsed from the JD by the brain). Output: selected component ids in the
order MMR picked them, plus a coverage matrix.

Selection is deterministic. Same inputs always yield the same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from matchbox.matching.bm25 import BM25Index
from matchbox.matching.embed import cosine_matrix
from matchbox.matching.mmr import mmr_select
from matchbox.matching.rrf import rrf_fuse

SEMANTIC_COVERAGE_FLOOR = 0.35
TOP_PER_REQUIREMENT = 8


@dataclass(slots=True)
class Component:
    id: int
    text: str
    experience_id: int  # for the per-role cap
    has_metric: bool = False


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

    relevance_by_component: dict[int, float] = {c.id: 0.0 for c in components}
    for j in target_indices:
        topN = fused_by_req[j][:TOP_PER_REQUIREMENT]
        for comp_idx, fused_score in topN:
            comp = components[comp_idx]
            prior = 1.0 + (0.15 if comp.has_metric else 0.0)
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
