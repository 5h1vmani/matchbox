"""Reciprocal Rank Fusion (RRF).

Combine multiple ranked lists of document ids using ranks, not raw
scores — robust when there is no calibration data and no need to
normalize across heterogeneous scorers.

  score(d) = sum over each ranking r of 1 / (k + rank_r(d))

`k=60` is the standard default. Documents missing from a given ranking
contribute zero to the sum.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_K = 60


def rrf_fuse(rankings: Sequence[Sequence[int]], k: int = DEFAULT_K) -> list[tuple[int, float]]:
    """Fuse rankings into one list sorted by descending RRF score.

    Each input ranking is a sequence of document ids, best first.
    Returns (doc_id, fused_score) pairs.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
