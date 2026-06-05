"""Tests for the evaluation harness.

Two parts:

* Unit tests for every metric in ``matchbox.eval.metrics`` — each pins a
  known input to a hand-computed output so a refactor cannot silently
  change the math.
* A smoke test that runs the full harness end-to-end on the shipped
  ``baseline.json`` with a deterministic bag-of-words ``FakeEmbedder`` —
  offline, no model download — and asserts the corpus is labeled so a
  correct algorithm scores and covers well.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, log2

import numpy as np
import pytest

from matchbox.eval.harness import (
    DEFAULT_CORPUS,
    build_profile_centroid,
    load_corpus,
    run_eval,
    score_corpus,
    select_corpus,
)
from matchbox.eval.metrics import (
    dcg_at_k,
    keyword_recall,
    mrr,
    ndcg_at_k,
    precision_at_k,
    requirement_coverage_rate,
)
from matchbox.matching.bm25 import tokenize

# ─── deterministic offline embedder (mirrors test_assemble_smoke.py) ───


@dataclass(slots=True)
class FakeEmbedder:
    """Bag-of-words embedder — deterministic, no network."""

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


def _corpus_vocab() -> list[str]:
    """Vocabulary spanning every string in the baseline corpus, so the
    FakeEmbedder gives non-trivial vectors to bullets, skills, JDs, and
    requirements alike."""
    corpus = load_corpus()
    texts: list[str] = [b.text for b in corpus.candidate.bullets]
    texts += corpus.candidate.skills
    for sc in corpus.scoring_cases:
        texts.append(str(sc.job.get("title", "")))
        texts.append(str(sc.job.get("jd_text", "")))
    for sel in corpus.selection_cases:
        for r in sel.requirements:
            texts.append(" ".join([r.text, *r.keywords, *r.variants]))
    return sorted({w for t in texts for w in tokenize(t)})


@pytest.fixture()
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(vocab=_corpus_vocab())


# ─── ndcg / dcg ───────────────────────────────────────────────────────


def test_dcg_at_k_known_value() -> None:
    # relevances [3, 2, 1]: 3/log2(2) + 2/log2(3) + 1/log2(4)
    expected = 3 / log2(2) + 2 / log2(3) + 1 / log2(4)
    assert isclose(dcg_at_k([3.0, 2.0, 1.0], 3), expected)


def test_dcg_respects_k_cutoff() -> None:
    # only the first item counts at k=1
    assert isclose(dcg_at_k([3.0, 2.0, 1.0], 1), 3.0)


def test_ndcg_perfect_ordering_is_one() -> None:
    assert ndcg_at_k([2.0, 1.0, 0.0], 3) == pytest.approx(1.0)


def test_ndcg_worst_ordering_is_below_one() -> None:
    # the relevant item is last; ndcg must drop below 1
    assert ndcg_at_k([0.0, 0.0, 2.0], 3) < 1.0


def test_ndcg_reversed_known_value() -> None:
    # actual [0,1,2] vs ideal [2,1,0]
    actual = 0 / log2(2) + 1 / log2(3) + 2 / log2(4)
    ideal = 2 / log2(2) + 1 / log2(3) + 0 / log2(4)
    assert ndcg_at_k([0.0, 1.0, 2.0], 3) == pytest.approx(actual / ideal)


def test_ndcg_all_zero_relevance_is_zero() -> None:
    assert ndcg_at_k([0.0, 0.0, 0.0], 3) == 0.0


def test_ndcg_empty_is_zero() -> None:
    assert ndcg_at_k([], 5) == 0.0


def test_ndcg_k_zero_is_zero() -> None:
    assert ndcg_at_k([2.0, 1.0], 0) == 0.0


# ─── precision@k ──────────────────────────────────────────────────────


def test_precision_at_k_half() -> None:
    assert precision_at_k([True, False, True, False], 4) == pytest.approx(0.5)


def test_precision_at_k_top_heavy() -> None:
    assert precision_at_k([True, True, False], 2) == pytest.approx(1.0)


def test_precision_at_k_clamps_denominator_to_list_length() -> None:
    # k larger than the list: denominator is the list length, not k
    assert precision_at_k([True, False], 10) == pytest.approx(0.5)


def test_precision_at_k_empty_is_zero() -> None:
    assert precision_at_k([], 3) == 0.0


def test_precision_at_k_zero_k_is_zero() -> None:
    assert precision_at_k([True, True], 0) == 0.0


# ─── mrr ──────────────────────────────────────────────────────────────


def test_mrr_first_relevant_is_one() -> None:
    assert mrr([True, False, False]) == pytest.approx(1.0)


def test_mrr_third_relevant_is_one_third() -> None:
    assert mrr([False, False, True]) == pytest.approx(1.0 / 3.0)


def test_mrr_none_relevant_is_zero() -> None:
    assert mrr([False, False]) == 0.0


def test_mrr_empty_is_zero() -> None:
    assert mrr([]) == 0.0


# ─── requirement coverage rate ────────────────────────────────────────


def test_requirement_coverage_rate_partial() -> None:
    assert requirement_coverage_rate([True, False, True, True]) == pytest.approx(0.75)


def test_requirement_coverage_rate_all_true() -> None:
    assert requirement_coverage_rate([True, True]) == pytest.approx(1.0)


def test_requirement_coverage_rate_empty_is_zero() -> None:
    assert requirement_coverage_rate([]) == 0.0


# ─── keyword recall ───────────────────────────────────────────────────


def test_keyword_recall_partial() -> None:
    assert keyword_recall(["python", "kubernetes"], ["python"]) == pytest.approx(0.5)


def test_keyword_recall_case_insensitive() -> None:
    assert keyword_recall(["Python", "SQL"], ["python", "sql"]) == pytest.approx(1.0)


def test_keyword_recall_dedupes_required() -> None:
    # "python" listed twice must not change the denominator
    assert keyword_recall(["python", "python", "sql"], ["python"]) == pytest.approx(0.5)


def test_keyword_recall_ignores_extra_present() -> None:
    assert keyword_recall(["python"], ["python", "rust", "go"]) == pytest.approx(1.0)


def test_keyword_recall_empty_required_is_zero() -> None:
    assert keyword_recall([], ["python"]) == 0.0


def test_keyword_recall_none_present_is_zero() -> None:
    assert keyword_recall(["python", "sql"], []) == 0.0


# ─── corpus loading ───────────────────────────────────────────────────


def test_baseline_corpus_loads() -> None:
    corpus = load_corpus()
    assert corpus.candidate.bullets, "candidate has no bullets"
    assert corpus.candidate.skills, "candidate has no skills"
    assert len(corpus.scoring_cases) >= 5
    assert corpus.selection_cases
    # target shape is the one score_job expects
    assert set(corpus.candidate.target) == {
        "role_families",
        "dream_companies",
        "locations",
        "exclusions",
    }


def test_load_corpus_rejects_empty(tmp_path: object) -> None:
    import json
    from pathlib import Path

    p = Path(str(tmp_path)) / "bad.json"
    p.write_text(json.dumps({"candidate": {"bullets": [], "skills": []}}))
    with pytest.raises(ValueError, match="scoring_cases"):
        load_corpus(p)


def test_default_corpus_path_exists() -> None:
    assert DEFAULT_CORPUS.exists()


# ─── harness smoke (offline) ──────────────────────────────────────────


def test_build_profile_centroid_is_unit_ish(fake_embedder: FakeEmbedder) -> None:
    corpus = load_corpus()
    centroid = build_profile_centroid(fake_embedder, corpus.candidate)
    assert centroid is not None
    assert centroid.shape == (fake_embedder.dim,)
    # mean of unit vectors: norm is in (0, 1]
    assert 0.0 < float(np.linalg.norm(centroid)) <= 1.0 + 1e-6


def test_score_corpus_ranks_relevant_first(fake_embedder: FakeEmbedder) -> None:
    corpus = load_corpus()
    ranked, metrics = score_corpus(corpus, fake_embedder)
    # the corpus is labeled so a correct scorer ranks perfectly
    assert metrics["ndcg_at_k"] == pytest.approx(1.0)
    assert metrics["precision_at_3"] == pytest.approx(1.0)
    assert metrics["mrr"] == pytest.approx(1.0)
    # the top-ranked job is one of the two strong (relevance 2) jobs
    assert ranked[0].relevance == 2
    # scores are sorted descending
    totals = [s.total for s in ranked]
    assert totals == sorted(totals, reverse=True)


def test_score_corpus_runs_lexical_only_without_embedder() -> None:
    corpus = load_corpus()
    ranked, metrics = score_corpus(corpus, None)
    # no semantic dimension when there is no embedder
    assert all(s.semantic_fit is None for s in ranked)
    # lexical signals alone still rank the corpus well
    assert metrics["mrr"] == pytest.approx(1.0)
    assert metrics["ndcg_at_k"] >= 0.9


def test_select_corpus_selects_expected_bullets(fake_embedder: FakeEmbedder) -> None:
    corpus = load_corpus()
    results, metrics = select_corpus(corpus, fake_embedder)
    assert metrics["selection_cases"] == 2.0
    # the hand-labeled "this bullet covers this requirement" bullets are
    # all actually selected (this is the selection-logic check; coverage
    # rate itself is sensitive to the toy embedder's calibration).
    assert metrics["mean_expected_bullets_selected"] == pytest.approx(1.0)
    # coverage and keyword recall are non-trivial with the toy embedder
    assert metrics["mean_requirement_coverage"] >= 0.5
    assert metrics["mean_keyword_recall"] >= 0.5
    assert {r.id for r in results} == {"data-platform-musthaves", "infra-musthaves"}


def test_run_eval_end_to_end_offline(fake_embedder: FakeEmbedder) -> None:
    corpus = load_corpus()
    report = run_eval(corpus, fake_embedder)
    m = report.metrics
    # every metric key the report renders is present and a float in range
    for key in (
        "ndcg_at_k",
        "ndcg_at_3",
        "precision_at_3",
        "mrr",
        "mean_requirement_coverage",
        "mean_expected_bullets_selected",
        "mean_keyword_recall",
    ):
        assert key in m
        assert 0.0 <= m[key] <= 1.0
    assert m["scoring_cases"] == float(len(corpus.scoring_cases))
    assert report.scored
    assert report.selection


def test_run_eval_lexical_only_skips_selection() -> None:
    corpus = load_corpus()
    report = run_eval(corpus, None)
    # selection needs embeddings; it is skipped (count 0) but the keys
    # still exist so the report renders.
    assert report.metrics["selection_cases"] == 0.0
    assert report.selection == []
    assert report.metrics["mrr"] == pytest.approx(1.0)


def test_cli_main_runs_offline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Force the lexical-only path so the CLI never reaches fastembed.
    monkeypatch.setenv("MATCHBOX_DISABLE_SEMANTIC", "1")
    from matchbox.eval import harness

    rc = harness.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Matchbox eval harness" in out
    assert "ndcg_at_k" in out


def test_cli_main_bad_corpus_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    from matchbox.eval import harness

    rc = harness.main(["/nonexistent/corpus.json"])
    assert rc == 2
    assert "could not load corpus" in capsys.readouterr().err
