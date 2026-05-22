"""Integration test for the real fastembed embedder.

Opt-in. Runs only when MATCHBOX_FASTEMBED_TEST=1 is set in the
environment, so CI and ordinary `pytest` runs do not pay the ~30 MB
model download cost on first use.

The contract this verifies (the one that until now had no test):

1. FastEmbedEmbedder can actually load the configured model.
2. encode() returns np.ndarray vectors of the documented dim (384).
3. Cosine similarity on a known related pair clears the
   SEMANTIC_COVERAGE_FLOOR comfortably. If this fails after a model
   change, the floor needs re-tuning.
4. Unrelated text does not score near-1.

Run:
    MATCHBOX_FASTEMBED_TEST=1 pytest tests/test_fastembed_integration.py -v
"""

from __future__ import annotations

import os

import pytest

try:
    import fastembed  # noqa: F401
except ImportError:  # pragma: no cover
    fastembed = None  # type: ignore[assignment]

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("MATCHBOX_FASTEMBED_TEST") != "1",
        reason="set MATCHBOX_FASTEMBED_TEST=1 to run (downloads ~30 MB on first use)",
    ),
    pytest.mark.skipif(fastembed is None, reason="fastembed not installed"),
]


def test_real_embedder_loads_and_encodes() -> None:
    from matchbox.matching.embed import (
        DEFAULT_MODEL_VERSION,
        FastEmbedEmbedder,
    )

    emb = FastEmbedEmbedder(model_version=DEFAULT_MODEL_VERSION)
    vecs = emb.encode(["hello world", "operating Kubernetes clusters"])
    assert len(vecs) == 2
    assert vecs[0].shape == (emb.dim,)


def test_real_embedder_separates_related_and_unrelated() -> None:
    from matchbox.matching.embed import FastEmbedEmbedder, cosine

    emb = FastEmbedEmbedder()
    a, b, c = emb.encode(
        [
            "Operated Kubernetes clusters across three regions for ML inference.",
            "Ran production K8s clusters serving real-time ML workloads.",
            "Wrote a children's book about magical squirrels.",
        ]
    )
    sim_related = cosine(a, b)
    sim_unrelated = cosine(a, c)
    # Related text should clear the matcher's semantic floor comfortably.
    from matchbox.matching.select import SEMANTIC_COVERAGE_FLOOR

    assert sim_related > max(
        SEMANTIC_COVERAGE_FLOOR, 0.6
    ), f"related cosine {sim_related:.3f} is below 0.6 floor; check the model"
    assert sim_related > sim_unrelated + 0.15, (
        f"related {sim_related:.3f} vs unrelated {sim_unrelated:.3f} "
        "is not separated enough; re-tune SEMANTIC_COVERAGE_FLOOR"
    )


def test_real_embedder_caches_in_db(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from matchbox.core.db import connect
    from matchbox.core.migrations import migrate
    from matchbox.matching.embed import FastEmbedEmbedder, cached_encode

    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    emb = FastEmbedEmbedder()

    items = [
        ("bullet", 1, "Operated Kubernetes clusters across three regions."),
        ("bullet", 2, "Built ETL pipelines in production."),
    ]
    first = cached_encode(conn, emb, items)
    assert len(first) == 2

    # Second call hits the cache: swap in an embedder that would fail
    # if encode() were called.
    class DeadEmbedder:
        model_version = emb.model_version
        dim = emb.dim

        def encode(self, texts):  # type: ignore[no-untyped-def]
            raise AssertionError("cache should have hit")

    second = cached_encode(conn, DeadEmbedder(), items)  # type: ignore[arg-type]
    for key in first:
        assert (second[key] == first[key]).all()
