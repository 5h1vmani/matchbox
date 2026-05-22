"""BM25 sparse retrieval — thin wrapper over `rank_bm25.BM25Okapi`.

Tokenization (per the plan):
- lowercase
- split on every non-alphanumeric character
- keep only ASCII letters and digits
- no stemming in v1
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Build once, query many."""

    def __init__(self, documents: list[str]) -> None:
        self.docs = documents
        self.tokenized = [tokenize(d) for d in documents]
        # BM25Okapi falls over on an empty corpus, so guard.
        self._bm25 = BM25Okapi(self.tokenized) if self.tokenized else None

    def score(self, query: str) -> list[float]:
        """Return a BM25 score per document, indexed by document position."""
        if self._bm25 is None:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return [0.0] * len(self.docs)
        return list(self._bm25.get_scores(q_tokens))
