"""Shared text utilities.

The tokenizer is intentionally narrow: lowercase, split on every
non-alphanumeric character, no stemming. It is the same function the
scoring rubric and the BM25 index use, so consistency between "did the
matcher see this token?" and "did the scorer see this token?" is
free.
"""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on every non-alphanumeric, no stemming.

    "Forward-Deployed Engineer · K8s" → ["forward", "deployed", "engineer", "k8s"].
    """
    return TOKEN_RE.findall(text.lower())
