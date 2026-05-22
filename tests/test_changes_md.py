"""Tests for changes.md — the "what's different vs. the library" diff."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from matchbox.assemble import assemble_one
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


@pytest.fixture()
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[sqlite3.Connection, Path, int]:
    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO profile (full_name, links_json) VALUES (?, ?)",
        ("Shiva Padakanti", "[]"),
    )
    exp = lib.add_experience(conn, company="Modal", role="FDE", start_date="2024-01")
    lib.add_bullet(
        conn, experience_id=exp.id, text="Operated Kubernetes clusters.", facts_verified=True
    )
    lib.add_bullet(conn, experience_id=exp.id, text="Built ETL pipelines.", facts_verified=True)
    lib.add_bullet(conn, experience_id=exp.id, text="Wrote PHP utilities.", facts_verified=True)

    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, status, requirements_json) "
        "VALUES (?, ?, ?, ?, ?, 'selected', ?)",
        (
            "Anthropic",
            "FDE",
            "https://x/1",
            "JD",
            "https://apply/1",
            json.dumps(
                {
                    "schema_version": 1,
                    "job_id": 1,
                    "model_version": "test",
                    "requirements": [
                        {
                            "type": "must-have",
                            "text": "Operate Kubernetes",
                            "keywords": ["kubernetes"],
                            "variants": [],
                        },
                    ],
                }
            ),
        ),
    )
    job_id = cur.lastrowid
    assert job_id is not None

    monkeypatch.setattr("matchbox.assemble.RUNS_DIR", tmp_path / "runs")
    return conn, tmp_path, job_id


def test_changes_md_is_written_with_selected_and_skipped(
    seeded: tuple[sqlite3.Connection, Path, int],
) -> None:
    conn, tmp_path, job_id = seeded
    vocab = sorted(
        set(
            w
            for t in [
                "Operated Kubernetes clusters.",
                "Built ETL pipelines.",
                "Wrote PHP utilities.",
                "Operate Kubernetes kubernetes",
            ]
            for w in tokenize(t)
        )
    )
    result = assemble_one(
        conn=conn,
        run_id="2026-05-22-001",
        job_id=job_id,
        palette="slate",
        font="source-serif",
        embedder=FakeEmbedder(vocab=vocab),
    )
    assert result.changes_md_path.exists()
    md = result.changes_md_path.read_text(encoding="utf-8")

    # The selected Kubernetes bullet appears under Selected.
    assert "Operated Kubernetes clusters." in md
    assert "Selected" in md or "**Selected:**" in md

    # The summary line counts library size and selected size.
    assert "Selected **" in md
    assert "of **3**" in md  # 3 verified bullets in the library

    # The job title is the H1.
    assert "Anthropic" in md
    assert "FDE" in md


def test_changes_md_lists_uncovered_must_haves(
    seeded: tuple[sqlite3.Connection, Path, int],
) -> None:
    conn, tmp_path, job_id = seeded
    # Replace requirements with one that the bullets cannot satisfy.
    conn.execute(
        "UPDATE job SET requirements_json = ?",
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "model_version": "t",
                    "requirements": [
                        {
                            "type": "must-have",
                            "text": "Build Terraform infrastructure.",
                            "keywords": ["terraform"],
                            "variants": [],
                        }
                    ],
                }
            ),
        ),
    )
    vocab = sorted(
        set(
            w
            for t in [
                "Operated Kubernetes clusters.",
                "Built ETL pipelines.",
                "Wrote PHP utilities.",
                "Build Terraform infrastructure terraform",
            ]
            for w in tokenize(t)
        )
    )
    result = assemble_one(
        conn=conn,
        run_id="2026-05-22-002",
        job_id=job_id,
        palette="slate",
        font="source-serif",
        embedder=FakeEmbedder(vocab=vocab),
    )
    md = result.changes_md_path.read_text(encoding="utf-8")
    assert "Uncovered must-haves" in md
    assert "Terraform" in md
