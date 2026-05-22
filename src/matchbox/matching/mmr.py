"""Maximal Marginal Relevance (MMR) selection.

Greedy selection that trades relevance against redundancy with a
candidate set:

  score(d) = lambda * rel(d) - (1 - lambda) * max_{s in selected} sim(d, s)

The relevance function takes a doc id and returns the best relevance
to any still-uncovered requirement (an external concern; pass it as a
callable). The similarity is between two doc embeddings.

This is ~15 lines of math; the rest is bookkeeping for the
"per-experience cap" constraint (≤ 4 bullets per role).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from matchbox.matching.embed import cosine

DEFAULT_LAMBDA = 0.5


def mmr_select(
    *,
    candidate_ids: list[int],
    embeddings: Mapping[int, np.ndarray],
    relevance: Callable[[int], float],
    k: int,
    lam: float = DEFAULT_LAMBDA,
    per_group_cap: int | None = None,
    group_of: Callable[[int], int] | None = None,
) -> list[int]:
    """Greedy MMR. Returns up to k selected ids in selection order.

    - relevance(doc_id): the best (component, requirement) relevance —
      caller decides whether to weight by has_metric, recency, etc.
    - per_group_cap + group_of: optional grouping constraint
      (e.g. "≤ 4 bullets per experience").
    """
    selected: list[int] = []
    pool = list(candidate_ids)
    group_counts: dict[int, int] = {}

    while pool and len(selected) < k:
        best_id: int | None = None
        best_score: float = float("-inf")
        for doc_id in pool:
            if per_group_cap is not None and group_of is not None:
                g = group_of(doc_id)
                if group_counts.get(g, 0) >= per_group_cap:
                    continue
            rel = relevance(doc_id)
            sim_term = 0.0
            if selected:
                sims = [cosine(embeddings[doc_id], embeddings[s]) for s in selected]
                sim_term = max(sims)
            score = lam * rel - (1.0 - lam) * sim_term
            if score > best_score:
                best_score = score
                best_id = doc_id
        if best_id is None:
            break
        selected.append(best_id)
        pool.remove(best_id)
        if per_group_cap is not None and group_of is not None:
            g = group_of(best_id)
            group_counts[g] = group_counts.get(g, 0) + 1
    return selected
