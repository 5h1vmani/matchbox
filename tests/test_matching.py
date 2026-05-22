"""Unit tests for the matching layer: BM25, RRF, MMR, select, coverage.

The Embedder Protocol lets us use a fake deterministic embedder so tests
do not hit fastembed.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

import numpy as np
import pytest

from matchbox.matching.bm25 import BM25Index, tokenize
from matchbox.matching.coverage import check_keyword_presence
from matchbox.matching.embed import cached_encode, content_hash, cosine, cosine_matrix
from matchbox.matching.mmr import mmr_select
from matchbox.matching.rrf import rrf_fuse
from matchbox.matching.select import (
    Component,
    Requirement,
    select_components,
)

# ─── BM25 ─────────────────────────────────────────────────────────────


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("Hello, World — K8s!") == ["hello", "world", "k8s"]


def test_bm25_ranks_more_relevant_higher() -> None:
    idx = BM25Index(
        [
            "We use python and sql daily.",
            "We are looking for a chef.",
            "We deploy on kubernetes with python.",
        ]
    )
    scores = idx.score("python kubernetes")
    # docs 0 and 2 mention python; doc 2 has both terms.
    assert scores[2] > scores[0]
    assert scores[2] > scores[1]


def test_bm25_empty_corpus_is_safe() -> None:
    idx = BM25Index([])
    assert idx.score("anything") == []


# ─── RRF ──────────────────────────────────────────────────────────────


def test_rrf_combines_two_rankings() -> None:
    rankings = [
        [1, 2, 3, 4],  # dense
        [3, 2, 1, 5],  # sparse
    ]
    fused = rrf_fuse(rankings, k=60)
    fused_dict = dict(fused)
    # 2 is mid-rank in both; 1 and 3 are top in one and mid in the other.
    assert fused_dict[1] == pytest.approx(1 / 61 + 1 / 63)
    assert fused_dict[2] == pytest.approx(1 / 62 + 1 / 62)
    # 5 only appears once
    assert fused_dict[5] == pytest.approx(1 / 64)


def test_rrf_sorted_descending() -> None:
    fused = rrf_fuse([[1, 2, 3]], k=60)
    assert [d for d, _ in fused] == [1, 2, 3]


# ─── MMR ──────────────────────────────────────────────────────────────


def test_mmr_returns_relevance_when_no_overlap() -> None:
    embs = {1: np.array([1.0, 0.0]), 2: np.array([0.0, 1.0]), 3: np.array([0.5, 0.5])}
    rel = {1: 0.9, 2: 0.8, 3: 0.85}
    selected = mmr_select(
        candidate_ids=[1, 2, 3],
        embeddings=embs,
        relevance=lambda i: rel[i],
        k=3,
        lam=1.0,  # full relevance, no diversity term
    )
    assert selected == [1, 3, 2]


def test_mmr_prefers_diverse_at_low_lambda() -> None:
    # two similar docs (1, 2) plus a different one (3). With low lambda,
    # MMR should pick 1 then 3 (diverse) before 2 (similar to 1).
    embs = {
        1: np.array([1.0, 0.0]),
        2: np.array([0.99, 0.1]),  # very similar to 1
        3: np.array([0.0, 1.0]),
    }
    rel = {1: 0.9, 2: 0.85, 3: 0.7}
    selected = mmr_select(
        candidate_ids=[1, 2, 3],
        embeddings=embs,
        relevance=lambda i: rel[i],
        k=2,
        lam=0.3,  # low lambda → diversity matters
    )
    assert selected == [1, 3]


def test_mmr_respects_per_group_cap() -> None:
    embs = {1: np.array([1.0]), 2: np.array([1.0]), 3: np.array([1.0]), 4: np.array([1.0])}
    rel = {1: 0.9, 2: 0.85, 3: 0.8, 4: 0.75}
    selected = mmr_select(
        candidate_ids=[1, 2, 3, 4],
        embeddings=embs,
        relevance=lambda i: rel[i],
        k=4,
        per_group_cap=1,
        group_of=lambda i: 1 if i in (1, 2) else 2,
    )
    # group 1 gets one, group 2 gets one — only two come back.
    assert len(selected) == 2
    assert 1 in selected
    assert 3 in selected


# ─── select_components end-to-end ─────────────────────────────────────


@dataclass(slots=True)
class FakeEmbedder:
    """A bag-of-words embedder for tests. Vector dim = number of words in
    the global vocabulary, value = TF count, normalized."""

    vocab: list[str]
    model_version: str = "fake-v1"

    @property
    def dim(self) -> int:
        return len(self.vocab)

    def encode(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for t in texts:
            tokens = tokenize(t)
            vec = np.zeros(self.dim, dtype=np.float32)
            for w in tokens:
                if w in self.vocab:
                    vec[self.vocab.index(w)] += 1.0
            n = float(np.linalg.norm(vec))
            if n > 0:
                vec /= n
            out.append(vec)
        return out


def test_select_picks_relevant_over_irrelevant() -> None:
    components = [
        Component(
            id=1,
            text="Built ETL pipelines processing 30M rows/day.",
            experience_id=10,
            has_metric=True,
        ),
        Component(id=2, text="Wrote PHP wordpress themes.", experience_id=10),
        Component(id=3, text="Deployed Kubernetes for ML inference at scale.", experience_id=11),
    ]
    requirements = [
        Requirement(text="Build data pipelines", type="must-have", keywords=["pipelines", "etl"]),
        Requirement(text="Operate Kubernetes clusters", type="must-have", keywords=["kubernetes"]),
    ]
    vocab = sorted(
        set(
            word
            for t in [
                *[c.text for c in components],
                *[r.text + " " + " ".join(r.keywords) for r in requirements],
            ]
            for word in tokenize(t)
        )
    )
    embedder = FakeEmbedder(vocab=vocab)
    comp_vecs = embedder.encode([c.text for c in components])
    req_vecs = embedder.encode([r.text + " " + " ".join(r.keywords) for r in requirements])

    result = select_components(
        components=components,
        component_embeddings=comp_vecs,
        requirements=requirements,
        requirement_embeddings=req_vecs,
        k=2,
        per_role_cap=4,
    )
    assert 1 in result.selected_ids  # ETL pipelines
    assert 3 in result.selected_ids  # Kubernetes
    assert 2 not in result.selected_ids  # PHP — irrelevant


def test_select_respects_per_role_cap() -> None:
    components = [Component(id=i, text=f"bullet {i}", experience_id=10) for i in range(1, 6)]
    requirements = [Requirement(text="anything", type="must-have")]
    vocab = sorted(set(word for c in components for word in tokenize(c.text)) | {"anything"})
    embedder = FakeEmbedder(vocab=vocab)
    comp_vecs = embedder.encode([c.text for c in components])
    req_vecs = embedder.encode([requirements[0].text])
    result = select_components(
        components=components,
        component_embeddings=comp_vecs,
        requirements=requirements,
        requirement_embeddings=req_vecs,
        k=5,
        per_role_cap=2,
    )
    # All five bullets are from the same experience; cap of 2 means at most 2 picked.
    assert len(result.selected_ids) == 2


def test_coverage_flag_is_true_when_supported() -> None:
    components = [Component(id=1, text="Operate Kubernetes clusters", experience_id=10)]
    requirements = [
        Requirement(text="Operate Kubernetes clusters", type="must-have", keywords=["kubernetes"])
    ]
    vocab = ["operate", "kubernetes", "clusters"]
    embedder = FakeEmbedder(vocab=vocab)
    result = select_components(
        components=components,
        component_embeddings=embedder.encode([components[0].text]),
        requirements=requirements,
        requirement_embeddings=embedder.encode([requirements[0].text]),
        k=1,
    )
    assert result.selected_ids == [1]
    assert result.covered == [True]


def test_coverage_flag_is_false_when_unsupported() -> None:
    components = [Component(id=1, text="Wrote PHP", experience_id=10)]
    requirements = [
        Requirement(text="Kubernetes clusters", type="must-have", keywords=["kubernetes"])
    ]
    vocab = ["wrote", "php", "kubernetes", "clusters"]
    embedder = FakeEmbedder(vocab=vocab)
    result = select_components(
        components=components,
        component_embeddings=embedder.encode([components[0].text]),
        requirements=requirements,
        requirement_embeddings=embedder.encode([requirements[0].text]),
        k=1,
    )
    assert result.covered == [False]


# ─── coverage / keyword presence ──────────────────────────────────────


def test_keyword_presence_finds_term() -> None:
    text = "Operated Kubernetes clusters across three regions."
    reqs = [
        Requirement(text="K8s ops", type="must-have", keywords=["kubernetes"]),
    ]
    rs = check_keyword_presence(text, reqs)
    assert rs[0].present is True
    assert rs[0].matched_term == "kubernetes"


def test_keyword_presence_uses_variants() -> None:
    text = "Operated K8s in production."
    reqs = [
        Requirement(
            text="Kubernetes",
            type="must-have",
            keywords=["kubernetes"],
            variants=["k8s"],
        ),
    ]
    rs = check_keyword_presence(text, reqs)
    assert rs[0].present is True
    assert rs[0].matched_term == "k8s"


def test_keyword_presence_is_word_boundary_safe() -> None:
    text = "We use k8some pattern."
    reqs = [Requirement(text="K8s", type="must-have", keywords=["k8s"])]
    rs = check_keyword_presence(text, reqs)
    assert rs[0].present is False


def test_keyword_presence_skips_non_musthaves() -> None:
    text = ""
    reqs = [Requirement(text="nice thing", type="nice", keywords=["nice"])]
    assert check_keyword_presence(text, reqs) == []


# ─── embed cache ──────────────────────────────────────────────────────


def test_embed_cache_round_trip(tmp_db: sqlite3.Connection) -> None:
    vocab = ["python", "rust", "sql"]
    embedder = FakeEmbedder(vocab=vocab)

    items = [
        ("bullet", 1, "I write python"),
        ("bullet", 2, "I write rust"),
    ]
    out1 = cached_encode(tmp_db, embedder, items)
    assert out1[("bullet", 1)].shape == (3,)

    # Second call hits the cache: change embedder so encode() would panic
    class DeadEmbedder:
        model_version = "fake-v1"
        dim = 3

        def encode(self, texts: list[str]) -> list[np.ndarray]:
            raise AssertionError("should not call encode on cache hit")

    out2 = cached_encode(tmp_db, DeadEmbedder(), items)  # type: ignore[arg-type]
    assert np.allclose(out2[("bullet", 1)], out1[("bullet", 1)])


def test_embed_cache_recomputes_on_text_change(tmp_db: sqlite3.Connection) -> None:
    vocab = ["python", "rust", "sql"]
    embedder = FakeEmbedder(vocab=vocab)
    cached_encode(tmp_db, embedder, [("bullet", 1, "I write python")])
    out = cached_encode(tmp_db, embedder, [("bullet", 1, "I write rust")])
    # vector for "rust" should be the rust direction
    expected = embedder.encode(["I write rust"])[0]
    assert np.allclose(out[("bullet", 1)], expected)
    # cache row's content_hash is now the rust hash, not the python one
    h = content_hash("I write rust")
    row = tmp_db.execute(
        "SELECT content_hash FROM embedding WHERE item_type='bullet' AND item_id=1"
    ).fetchone()
    assert row["content_hash"] == h


# ─── cosine ───────────────────────────────────────────────────────────


def test_cosine_basic() -> None:
    a = np.array([1.0, 0.0])
    b = np.array([1.0, 0.0])
    c = np.array([0.0, 1.0])
    assert math.isclose(cosine(a, b), 1.0)
    assert math.isclose(cosine(a, c), 0.0)


def test_cosine_matrix_shape() -> None:
    rows = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    cols = [np.array([1.0, 0.0])]
    m = cosine_matrix(rows, cols)
    assert m.shape == (2, 1)
    assert math.isclose(float(m[0, 0]), 1.0)
    assert math.isclose(float(m[1, 0]), 0.0, abs_tol=1e-6)
