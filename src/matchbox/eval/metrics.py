"""Pure ranking and coverage metrics for the eval harness.

Every function here is a pure function of its arguments: no I/O, no
globals, no side effects. They are the yardsticks the harness applies to
the output of the (unchanged) scoring and matching code.

Two families:

* **Ranking quality** (scoring): ``ndcg_at_k``, ``precision_at_k``,
  ``mrr``. The input is a list already ordered by the system's predicted
  score (rank 0 = the system's top pick), carrying the *true* relevance
  label of the item at that rank.
* **Coverage** (selection): ``requirement_coverage_rate``,
  ``keyword_recall``. These score how completely a selection satisfied a
  requirement set.

Conventions:

* ``k`` is a count of top ranks. ``k <= 0`` is treated as "no cutoff is
  meaningful" and returns ``0.0`` rather than raising, so a caller that
  derives ``k`` from a possibly-empty list never blows up.
* Graded relevance is ``float`` (typically 0/1/2). Binary relevance is
  ``bool``.
* An empty input returns ``0.0`` (vacuously no quality / no coverage),
  never ``NaN`` and never a divide-by-zero.
"""

from __future__ import annotations

from math import log2

__all__ = [
    "dcg_at_k",
    "keyword_recall",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "requirement_coverage_rate",
]


def dcg_at_k(relevances: list[float], k: int) -> float:
    """Discounted cumulative gain over the first ``k`` ranked items.

    ``relevances`` is ordered by the system's predicted rank (index 0 is
    the top result). The standard gain ``rel_i`` with the standard log2
    position discount is used::

        DCG@k = sum_{i=1..k} rel_i / log2(i + 1)

    so the item at rank 1 (index 0) is undiscounted, rank 2 is divided by
    log2(3), and so on.
    """
    if k <= 0:
        return 0.0
    total = 0.0
    for i, rel in enumerate(relevances[:k]):
        total += rel / log2(i + 2)  # i is 0-based; position is i + 1
    return total


def ndcg_at_k(relevances: list[float], k: int) -> float:
    """Normalized DCG@k in ``[0.0, 1.0]``.

    The system ordering's DCG is divided by the ideal DCG (the same
    relevance values sorted descending). ``1.0`` means the system put the
    most-relevant items first; ``0.0`` means there was no relevance to
    capture (or ``k <= 0``).

    Negative relevances are not expected; if supplied, the ideal ordering
    is still "sorted descending", which keeps the ratio well defined.
    """
    if k <= 0 or not relevances:
        return 0.0
    actual = dcg_at_k(relevances, k)
    ideal = dcg_at_k(sorted(relevances, reverse=True), k)
    if ideal == 0.0:
        return 0.0
    return actual / ideal


def precision_at_k(labels: list[bool], k: int) -> float:
    """Fraction of the top ``k`` ranked items that are relevant.

    ``labels`` is ordered by predicted rank; ``True`` means the item at
    that rank is relevant. The denominator is ``min(k, len(labels))`` so a
    short result list is not penalised for ranks that do not exist.
    """
    if k <= 0 or not labels:
        return 0.0
    top = labels[:k]
    denom = len(top)
    if denom == 0:
        return 0.0
    return sum(1 for hit in top if hit) / denom


def mrr(labels: list[bool]) -> float:
    """Reciprocal rank of the first relevant item (single ranked list).

    ``labels`` is ordered by predicted rank. Returns ``1 / rank`` of the
    first ``True`` (rank is 1-based), or ``0.0`` if nothing is relevant.
    The classic MRR averages this over many queries; the harness does the
    averaging across cases, so this is the per-query term.
    """
    for i, hit in enumerate(labels):
        if hit:
            return 1.0 / (i + 1)
    return 0.0


def requirement_coverage_rate(covered: list[bool]) -> float:
    """Fraction of requirements that a selection covered, in ``[0, 1]``.

    ``covered[i]`` is ``True`` when requirement ``i`` was satisfied. An
    empty list (no requirements) returns ``0.0``.
    """
    if not covered:
        return 0.0
    return sum(1 for c in covered if c) / len(covered)


def keyword_recall(required: list[str], present: list[str]) -> float:
    """Fraction of required keywords that are present, in ``[0, 1]``.

    Case-insensitive and whitespace-trimmed; duplicates in ``required``
    are collapsed so a keyword listed twice cannot inflate the
    denominator. An empty ``required`` list returns ``0.0`` (nothing was
    asked for, so there is nothing to recall).
    """
    required_set = {kw.strip().lower() for kw in required if kw.strip()}
    if not required_set:
        return 0.0
    present_set = {kw.strip().lower() for kw in present if kw.strip()}
    hits = sum(1 for kw in required_set if kw in present_set)
    return hits / len(required_set)
