"""Tests for the recency weight and one-page word budget in select_components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pytest

from matchbox.matching.bm25 import tokenize
from matchbox.matching.select import (
    DEFAULT_WORD_BUDGET,
    Component,
    Requirement,
    _recency_weight,
    _years_since,
    select_components,
)

NOW = datetime(2026, 5, 22, tzinfo=UTC)


# ─── recency math ─────────────────────────────────────────────────────


def test_years_since_present_is_zero() -> None:
    assert _years_since(None, now=NOW) == 0.0
    assert _years_since("present", now=NOW) == 0.0
    assert _years_since("Present", now=NOW) == 0.0


def test_years_since_full_date() -> None:
    assert _years_since("2024-05-22", now=NOW) == pytest.approx(2.0, abs=0.01)


def test_years_since_year_only() -> None:
    # "2022" → Jan 1, 2022. Roughly 4.4 years from 2026-05-22.
    y = _years_since("2022", now=NOW)
    assert 4.0 < y < 4.7


def test_years_since_malformed_returns_zero() -> None:
    assert _years_since("nonsense", now=NOW) == 0.0
    assert _years_since("2024-13-99", now=NOW) == 0.0


def test_recency_weight_monotonic() -> None:
    w_now = _recency_weight(None, now=NOW)
    w_recent = _recency_weight("2025-05-22", now=NOW)
    w_old = _recency_weight("2020-05-22", now=NOW)
    w_ancient = _recency_weight("2010-05-22", now=NOW)
    assert w_now == 1.0
    assert w_recent < w_now
    assert w_old < w_recent
    assert w_ancient < w_old
    # Floor: even ancient roles keep at least 0.05.
    assert w_ancient >= 0.05


# ─── selection prefers recent over equally-relevant ancient ──────────


@dataclass(slots=True)
class FakeEmbedder:
    """Bag-of-words; identical vectors for identical texts so two bullets
    that read the same have identical relevance pre-priors."""

    vocab: list[str]
    model_version: str = "fake-v1"

    @property
    def dim(self) -> int:
        return len(self.vocab)

    def encode(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            for w in tokenize(t):
                if w in self.vocab:
                    v[self.vocab.index(w)] += 1.0
            n = float(np.linalg.norm(v))
            if n > 0:
                v /= n
            out.append(v)
        return out


def test_recent_role_outranks_ancient_for_same_text() -> None:
    """Same text, different end_dates. Recent wins."""
    components = [
        Component(id=1, text="Operated Kubernetes clusters.", experience_id=10, end_date="present"),
        Component(id=2, text="Operated Kubernetes clusters.", experience_id=20, end_date="2015-01"),
    ]
    requirements = [Requirement(text="Kubernetes ops", type="must-have", keywords=["kubernetes"])]
    vocab = ["operated", "kubernetes", "clusters", "ops"]
    emb = FakeEmbedder(vocab=vocab)
    result = select_components(
        components=components,
        component_embeddings=emb.encode([c.text for c in components]),
        requirements=requirements,
        requirement_embeddings=emb.encode([requirements[0].text + " kubernetes"]),
        k=1,
        per_role_cap=4,
        now=NOW,
    )
    assert result.selected_ids == [1]


def test_relevance_dict_carries_recency_signal() -> None:
    components = [
        Component(id=1, text="Operated Kubernetes.", experience_id=10, end_date="present"),
        Component(id=2, text="Operated Kubernetes.", experience_id=20, end_date="2010-01"),
    ]
    requirements = [Requirement(text="Kubernetes", type="must-have", keywords=["kubernetes"])]
    vocab = ["operated", "kubernetes"]
    emb = FakeEmbedder(vocab=vocab)
    result = select_components(
        components=components,
        component_embeddings=emb.encode([c.text for c in components]),
        requirements=requirements,
        requirement_embeddings=emb.encode([requirements[0].text]),
        k=2,
        now=NOW,
    )
    assert result.relevance_by_component[1] > result.relevance_by_component[2]


# ─── one-page word budget ─────────────────────────────────────────────


def test_budget_drops_weakest_when_over() -> None:
    """Force the budget low enough that not every bullet fits. Weakest
    by relevance drops first."""
    components = [
        Component(
            id=1,
            text="Operated Kubernetes clusters with terraform pipelines etl runbooks.",
            experience_id=10,
            end_date="present",
        ),
        Component(
            id=2,
            text="Built pipelines etl for kubernetes platform daily.",
            experience_id=10,
            end_date="present",
        ),
        Component(
            id=3,
            text="Wrote tedious admin documentation pages and onboarding decks for new hires.",
            experience_id=10,
            end_date="present",
        ),
    ]
    requirements = [
        Requirement(text="Operate Kubernetes", type="must-have", keywords=["kubernetes"])
    ]
    vocab = sorted(set(w for c in components for w in tokenize(c.text)) | {"operate", "kubernetes"})
    emb = FakeEmbedder(vocab=vocab)
    # Word budget chosen to allow about two bullets (~10 words each → 20).
    result = select_components(
        components=components,
        component_embeddings=emb.encode([c.text for c in components]),
        requirements=requirements,
        requirement_embeddings=emb.encode([requirements[0].text + " kubernetes"]),
        k=3,
        word_budget=18,
        now=NOW,
    )
    # The least-relevant bullet (id=3, no kubernetes) is dropped.
    assert 3 not in result.selected_ids
    # At least the most-relevant one is kept.
    assert 1 in result.selected_ids or 2 in result.selected_ids


def test_budget_is_a_noop_when_under() -> None:
    components = [
        Component(id=1, text="Short bullet.", experience_id=10, end_date="present"),
        Component(id=2, text="Another short.", experience_id=10, end_date="present"),
    ]
    requirements = [Requirement(text="anything", type="must-have")]
    vocab = sorted(set(w for c in components for w in tokenize(c.text)) | {"anything"})
    emb = FakeEmbedder(vocab=vocab)
    result = select_components(
        components=components,
        component_embeddings=emb.encode([c.text for c in components]),
        requirements=requirements,
        requirement_embeddings=emb.encode([requirements[0].text]),
        k=2,
        word_budget=DEFAULT_WORD_BUDGET,
        now=NOW,
    )
    assert len(result.selected_ids) == 2
