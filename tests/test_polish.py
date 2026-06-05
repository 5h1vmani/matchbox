"""Tests for the keyword-alignment polish pass (design section 5d)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from matchbox.assemble import assemble_one, polish_run
from matchbox.core import library as lib
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.matching.bm25 import tokenize
from matchbox.polish import (
    apply_polish,
    validate_polish_payload,
    validate_voice,
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


# ─── voice-rules unit tests ──────────────────────────────────────────


def test_validate_voice_clean() -> None:
    assert (
        validate_voice(
            "Operated Kubernetes clusters across three regions for the platform team daily."
        )
        == []
    )


def test_validate_voice_banned_word() -> None:
    out = validate_voice("Used leverage to drive results.")
    rules = {v.rule for v in out}
    assert "banned_word" in rules


def test_validate_voice_banned_opener_with_placeholder() -> None:
    out = validate_voice(
        "As a engineer with 5 years of experience I will do great things and add value."
    )
    rules = {v.rule for v in out}
    assert "banned_opener" in rules


def test_validate_voice_em_dash() -> None:
    out = validate_voice("Operated Kubernetes clusters — across three regions.")
    rules = {v.rule for v in out}
    assert "no_em_dashes" in rules


def test_validate_voice_contraction() -> None:
    out = validate_voice("Operated Kubernetes; we're across three regions everywhere now.")
    rules = {v.rule for v in out}
    assert "no_contractions" in rules


def test_validate_voice_too_short_too_long() -> None:
    assert any(v.rule == "too_short" for v in validate_voice("Tiny."))
    long = " ".join(["word"] * 40)
    assert any(v.rule == "too_long" for v in validate_voice(long))


# ─── schema validation ────────────────────────────────────────────────


def test_validate_polish_payload_ok() -> None:
    errors = validate_polish_payload(
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "job_id": 1,
            "polished": [
                {"id": 7, "text": "Built and ran ETL data pipelines in production daily."}
            ],
        }
    )
    assert errors == []


def test_validate_polish_payload_rejects_bad_shape() -> None:
    errors = validate_polish_payload(
        {"schema_version": 1, "run_id": "x", "job_id": 1, "polished": []}
    )
    assert errors  # minItems: 1


# ─── apply_polish unit tests ─────────────────────────────────────────


@pytest.fixture()
def db_with_selection(tmp_path: Path) -> tuple[sqlite3.Connection, Path, list[int]]:
    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    exp = lib.add_experience(conn, company="Modal", role="FDE", start_date="2024-01")
    b1 = lib.add_bullet(
        conn, experience_id=exp.id, text="Built data pipelines in production.", facts_verified=True
    )
    b2 = lib.add_bullet(
        conn, experience_id=exp.id, text="Operated Kubernetes clusters.", facts_verified=True
    )
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Wrote PHP utilities for the legacy app.",
        facts_verified=True,
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    cv_json = {
        "schema_version": 1,
        "profile": {"name": "Shiva Padakanti", "headline": "", "contact": []},
        "summary": "",
        "experiences": [
            {
                "company": "Modal",
                "role": "FDE",
                "start_date": "2024-01",
                "end_date": "present",
                "location": None,
                "bullets": [
                    "Built data pipelines in production.",
                    "Operated Kubernetes clusters.",
                ],
            }
        ],
        "projects": [],
        "skills": [],
        "education": [],
    }
    (out_dir / "cv.json").write_text(json.dumps(cv_json))
    return conn, out_dir, [b1.id, b2.id]  # only b1, b2 selected; b3 is in lib only


def test_apply_polish_replaces_selected_bullet(
    db_with_selection: tuple[sqlite3.Connection, Path, list[int]],
) -> None:
    conn, out_dir, selected = db_with_selection
    payload = {
        "schema_version": 1,
        "run_id": "r",
        "job_id": 1,
        "polished": [
            {
                "id": selected[0],
                "text": "Built and ran ETL data pipelines daily in production.",
                "original_text": "Built data pipelines in production.",
                "covers": ["etl"],
            }
        ],
    }
    applied, rejected, new_cv = apply_polish(
        conn=conn, out_dir=out_dir, selected_ids=selected, payload=payload
    )
    assert len(applied) == 1
    assert rejected == []
    bullets = new_cv["experiences"][0]["bullets"]
    assert "Built and ran ETL" in bullets[0]
    # cv.json on disk also updated.
    on_disk = json.loads((out_dir / "cv.json").read_text())
    assert on_disk["experiences"][0]["bullets"][0] == bullets[0]


def test_apply_polish_rejects_non_selected_bullet(
    db_with_selection: tuple[sqlite3.Connection, Path, list[int]],
) -> None:
    conn, out_dir, selected = db_with_selection
    payload = {
        "schema_version": 1,
        "run_id": "r",
        "job_id": 1,
        "polished": [
            {
                "id": 99999,  # not in selected
                "text": "Built and ran ETL data pipelines daily in production.",
            }
        ],
    }
    applied, rejected, _ = apply_polish(
        conn=conn, out_dir=out_dir, selected_ids=selected, payload=payload
    )
    assert applied == []
    assert rejected and rejected[0].violations[0].rule == "not_selected"


def test_apply_polish_rejects_banned_word(
    db_with_selection: tuple[sqlite3.Connection, Path, list[int]],
) -> None:
    conn, out_dir, selected = db_with_selection
    payload = {
        "schema_version": 1,
        "run_id": "r",
        "job_id": 1,
        "polished": [
            {
                "id": selected[0],
                "text": "Leveraged ETL data pipelines daily in production to drive value.",
            }
        ],
    }
    applied, rejected, _ = apply_polish(
        conn=conn, out_dir=out_dir, selected_ids=selected, payload=payload
    )
    assert applied == []
    assert rejected
    assert any(v.rule == "banned_word" for v in rejected[0].violations)


# ─── end-to-end polish_run ───────────────────────────────────────────


def test_polish_run_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matchbox.assemble.RUNS_DIR", tmp_path / "runs")

    db = tmp_path / "matchbox.db"
    conn = connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO profile (full_name, links_json) VALUES (?, ?)",
        ("Shiva Padakanti", "[]"),
    )
    exp = lib.add_experience(conn, company="Modal", role="FDE", start_date="2024-01")
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Built data pipelines daily in production at scale.",
        facts_verified=True,
    )
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Operated Kubernetes clusters across three regions for ML.",
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
                    "text": "Build ETL pipelines.",
                    "keywords": ["etl"],
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
        set(
            w
            for t in [
                "Built data pipelines daily in production at scale.",
                "Operated Kubernetes clusters across three regions for ML.",
                "Build ETL pipelines. etl",
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

    # Confirm: "etl" is missing from the pre-polish PDF text.
    from pypdf import PdfReader

    text_before = "\n".join((p.extract_text() or "") for p in PdfReader(str(result.cv_path)).pages)
    assert "etl" not in text_before.lower()

    # Brain writes a polish.json that carries the "etl" term.
    polish_payload = {
        "schema_version": 1,
        "run_id": "2026-05-22-001",
        "job_id": job_id,
        "polished": [
            {
                "id": result.selected_component_ids[0],
                "text": "Built ETL data pipelines daily in production at scale.",
                "original_text": "Built data pipelines daily in production at scale.",
                "covers": ["etl"],
            }
        ],
    }
    summary = polish_run(
        conn=conn,
        run_id="2026-05-22-001",
        job_id=job_id,
        palette="slate",
        font="source-serif",
        payload=polish_payload,
    )
    assert len(summary["applied"]) == 1
    assert summary["rejected"] == []

    # Post-polish PDF now contains "etl".
    text_after = "\n".join((p.extract_text() or "") for p in PdfReader(str(result.cv_path)).pages)
    assert "etl" in text_after.lower()

    # coverage.json reflects the new keyword presence.
    coverage = json.loads(result.coverage_report_path.read_text())
    by_text = {kp["requirement"]: kp for kp in coverage["keyword_presence"]}
    assert by_text["Build ETL pipelines."]["present"] is True

    # changes.md now has a Polished section.
    changes = result.changes_md_path.read_text()
    assert "## Polished" in changes
    assert "covers: etl" in changes
