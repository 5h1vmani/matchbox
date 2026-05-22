"""Dense embeddings — fastembed wrapper with a Protocol seam.

Production uses BAAI/bge-small-en-v1.5 via fastembed (384-dim, ONNX,
~30 MB on first download). Tests inject a fake embedder via the
Protocol so the unit-test path does not need the model.

Caches vectors in the `embedding` table keyed by (item_type, item_id,
model_version, content_hash). A content edit changes the hash and
triggers a clean recompute.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Protocol

import numpy as np

DEFAULT_MODEL_VERSION = "bge-small-en-v1.5"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Embedder(Protocol):
    """Interface for any model that turns strings into vectors.

    `model_version` is recorded in the `embedding` table so a model
    change triggers a clean recompute.
    """

    model_version: str
    dim: int

    def encode(self, texts: list[str]) -> list[np.ndarray]: ...


@dataclass(slots=True)
class FastEmbedEmbedder:
    """Lazy-loaded fastembed embedder.

    The actual TextEmbedding object downloads the model on first use; we
    therefore defer construction until encode() is called so a test that
    never touches embeddings does not pay the cost.
    """

    model_version: str = DEFAULT_MODEL_VERSION
    dim: int = 384
    _model: object = None

    def _ensure(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding  # heavy; lazy import

            self._model = TextEmbedding(model_name=f"BAAI/{self.model_version}")
        return self._model

    def encode(self, texts: list[str]) -> list[np.ndarray]:
        model = self._ensure()
        # fastembed returns a generator of np.ndarray; we materialize it.
        vectors = list(model.embed(texts))  # type: ignore[attr-defined]
        return [np.asarray(v, dtype=np.float32) for v in vectors]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def cosine_matrix(rows: list[np.ndarray], cols: list[np.ndarray]) -> np.ndarray:
    """Returns an R×C matrix of cosine similarities."""
    if not rows or not cols:
        return np.zeros((len(rows), len(cols)), dtype=np.float32)
    R = np.vstack(rows).astype(np.float32)
    C = np.vstack(cols).astype(np.float32)
    R_norm = R / np.clip(np.linalg.norm(R, axis=1, keepdims=True), 1e-12, None)
    C_norm = C / np.clip(np.linalg.norm(C, axis=1, keepdims=True), 1e-12, None)
    out: np.ndarray = R_norm @ C_norm.T
    return out


# ─── caching layer ────────────────────────────────────────────────────


def vector_to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def vector_from_blob(b: bytes, dim: int) -> np.ndarray:
    arr = np.frombuffer(b, dtype=np.float32)
    if arr.size != dim:
        raise ValueError(f"embedding dim mismatch: stored {arr.size}, embedder dim {dim}")
    return arr


def cached_encode(
    conn: sqlite3.Connection,
    embedder: Embedder,
    items: list[tuple[str, int, str]],
) -> dict[tuple[str, int], np.ndarray]:
    """Embed a list of (item_type, item_id, text) tuples, caching results
    in the `embedding` table. Returns a dict (item_type, item_id) -> vector.
    """
    out: dict[tuple[str, int], np.ndarray] = {}
    to_encode: list[tuple[str, int, str, str]] = []

    for item_type, item_id, text in items:
        h = content_hash(text)
        row = conn.execute(
            """
            SELECT vector FROM embedding
             WHERE item_type = ? AND item_id = ?
               AND model_version = ? AND content_hash = ?
            """,
            (item_type, item_id, embedder.model_version, h),
        ).fetchone()
        if row is not None:
            out[(item_type, item_id)] = vector_from_blob(row[0], embedder.dim)
        else:
            to_encode.append((item_type, item_id, text, h))

    if to_encode:
        vectors = embedder.encode([t[2] for t in to_encode])
        for (item_type, item_id, _text, h), vec in zip(to_encode, vectors, strict=True):
            out[(item_type, item_id)] = vec
            conn.execute(
                """
                INSERT OR REPLACE INTO embedding
                    (item_type, item_id, model_version, content_hash, vector)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_type, item_id, embedder.model_version, h, vector_to_blob(vec)),
            )

    return out
