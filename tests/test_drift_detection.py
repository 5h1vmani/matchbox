"""Tests for stale cv.json detection on re-render.

Reflection said: re_render_cv blasts a new PDF from whatever cv.json
says, even if the user edited the underlying bullet in /library.
drift_check + re_render_cv's tuple return surface the divergence.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from matchbox.assemble import assemble_one, drift_check, re_render_cv
from matchbox.core import library as lib
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.matching.bm25 import tokenize

pytestmark = pytest.mark.skipif(
    shutil.which("typst") is None,
    reason="typst not installed",
)


@dataclass(slots=True)
class FakeEmbedder:
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


def _seed_assembled_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[sqlite3.Connection, str, int, int]:
    """Run assemble_one end to end so cv.json carries fingerprints."""
    monkeypatch.setattr("matchbox.assemble.RUNS_DIR", tmp_path / "runs")
    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO profile (full_name, links_json) VALUES (?, ?)",
        ("Shiva", "[]"),
    )
    exp = lib.add_experience(conn, company="Modal", role="FDE", start_date="2024-01")
    b1 = lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Operated Kubernetes clusters across three regions for ML.",
        facts_verified=True,
    )
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Built data pipelines in production daily.",
        facts_verified=True,
    )

    requirements_json = json.dumps(
        {
            "schema_version": 1,
            "job_id": 1,
            "model_version": "t",
            "requirements": [
                {
                    "type": "must-have",
                    "text": "Operate Kubernetes",
                    "keywords": ["kubernetes"],
                }
            ],
        }
    )
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, status, requirements_json) "
        "VALUES (?, ?, ?, ?, ?, 'selected', ?)",
        ("Anthropic", "FDE", "https://x/1", "JD", "https://apply/1", requirements_json),
    )
    job_id = cur.lastrowid
    assert job_id is not None

    vocab = sorted(
        {
            w
            for t in [
                "Operated Kubernetes clusters across three regions for ML.",
                "Built data pipelines in production daily.",
                "Operate Kubernetes kubernetes",
            ]
            for w in tokenize(t)
        }
    )
    assemble_one(
        conn=conn,
        run_id="2026-05-22-001",
        job_id=job_id,
        palette="slate",
        font="source-serif",
        embedder=FakeEmbedder(vocab=vocab),
    )
    return conn, "2026-05-22-001", job_id, b1.id


def test_cv_json_carries_fingerprints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn, run_id, job_id, _ = _seed_assembled_run(tmp_path, monkeypatch)
    cv_json = json.loads(
        (tmp_path / "runs" / run_id / "output" / str(job_id) / "cv.json").read_text()
    )
    fps = cv_json.get("_selected_bullets")
    assert fps and all("id" in fp and "text_hash" in fp for fp in fps)


def test_re_render_returns_empty_drift_when_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, run_id, job_id, _ = _seed_assembled_run(tmp_path, monkeypatch)
    _, drift = re_render_cv(run_id=run_id, job_id=job_id, palette="forest", font="inter", conn=conn)
    assert drift == []


def test_re_render_detects_edited_bullet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn, run_id, job_id, b1_id = _seed_assembled_run(tmp_path, monkeypatch)
    # Edit the underlying bullet so cv.json's fingerprint no longer matches.
    lib.update_bullet(conn, b1_id, text="Completely different sentence about K8s.")
    _, drift = re_render_cv(
        run_id=run_id, job_id=job_id, palette="slate", font="source-serif", conn=conn
    )
    drifted_ids = {d["id"] for d in drift}
    assert b1_id in drifted_ids


def test_drift_check_handles_deleted_bullet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, run_id, job_id, b1_id = _seed_assembled_run(tmp_path, monkeypatch)
    lib.delete_bullet(conn, b1_id)
    cv_json = json.loads(
        (tmp_path / "runs" / run_id / "output" / str(job_id) / "cv.json").read_text()
    )
    drift = drift_check(conn=conn, cv_json=cv_json)
    assert any(d["id"] == b1_id and d["db_text"] is None for d in drift)
