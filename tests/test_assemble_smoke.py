"""End-to-end smoke test for the matching + assembly + weasyprint path.

This is the M5 mandatory check (section 14 of v0.3-design.md):
"asserts a non-empty, well-formed PDF whose extracted text contains
the expected keywords — the single check whose absence let v0.2 ship a
blank page."
"""

from __future__ import annotations

import json
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


@pytest.fixture()
def seeded_db_and_runs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[sqlite3.Connection, Path, int]:
    db_path = tmp_path / "matchbox.db"
    conn = connect(db_path)
    migrate(conn)

    # Profile
    conn.execute(
        """
        INSERT INTO profile (full_name, email, location, links_json, headline)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Shiva Padakanti", "shiva@example.com", "Remote", "[]", "Generalist engineer"),
    )

    # Two experiences with verified bullets that mention the keywords we will
    # require in the JD. These are the bullets the matcher should pick.
    exp1 = lib.add_experience(
        conn, company="Modal", role="Forward Deployed Engineer", start_date="2024-01"
    )
    exp2 = lib.add_experience(
        conn, company="OldCo", role="Junior Engineer", start_date="2020-06", end_date="2023-12"
    )

    bullets_to_add = [
        (exp1.id, "Built ETL pipelines processing 30M rows per day in Python.", True),
        (exp1.id, "Operated Kubernetes clusters across three regions.", False),
        (exp1.id, "Mentored two junior engineers on ML systems.", False),
        (exp2.id, "Shipped a Rails monolith and wrote ad hoc PHP utilities.", False),
        (exp2.id, "Wrote SQL ETL jobs for the analytics team.", False),
    ]
    for exp_id, text, has_metric in bullets_to_add:
        b = lib.add_bullet(
            conn, experience_id=exp_id, text=text, has_metric=has_metric, facts_verified=True
        )
        # Tag a couple to exercise the path.
        if "Kubernetes" in text:
            lib.attach_tag(conn, item_type="bullet", item_id=b.id, facet="tech", value="kubernetes")
        if "Python" in text:
            lib.attach_tag(conn, item_type="bullet", item_id=b.id, facet="tech", value="python")

    # A skill in the library — appears as a "Skills" section.
    lib.add_skill(conn, name="Python", category="Languages", proficiency="expert")
    lib.add_skill(conn, name="Kubernetes", category="Infra", proficiency="fluent")

    # A summary variant.
    lib.add_summary(conn, label="ml-focus", text="ML-leaning generalist engineer.")

    # A job (status='selected', already through the triage UI).
    cur = conn.execute(
        """
        INSERT INTO job (company, title, url, jd_text, apply_url, location, status, requirements_json, requirements_model)
        VALUES (?, ?, ?, ?, ?, ?, 'selected', ?, ?)
        """,
        (
            "Anthropic",
            "Forward Deployed Engineer",
            "https://job.example/anthropic-fde",
            "We are looking for someone to build ETL pipelines and operate Kubernetes.",
            "https://apply.example/anthropic-fde",
            "Remote",
            json.dumps(
                {
                    "schema_version": 1,
                    "job_id": 1,
                    "model_version": "test-model-v1",
                    "requirements": [
                        {
                            "type": "must-have",
                            "text": "Build and operate data pipelines.",
                            "keywords": ["pipelines", "etl"],
                            "variants": [],
                        },
                        {
                            "type": "must-have",
                            "text": "Operate Kubernetes clusters in production.",
                            "keywords": ["kubernetes"],
                            "variants": ["k8s"],
                        },
                        {
                            "type": "responsibility",
                            "text": "Mentor engineers.",
                            "keywords": ["mentor"],
                            "variants": [],
                        },
                    ],
                }
            ),
            "test-model-v1",
        ),
    )
    assert cur.lastrowid is not None
    job_id = cur.lastrowid

    # Re-point runs/ at tmp_path so the test does not pollute the repo.
    from matchbox import assemble as assemble_mod

    monkeypatch.setattr(assemble_mod, "RUNS_DIR", tmp_path / "runs")
    (tmp_path / "runs").mkdir(exist_ok=True)

    return conn, tmp_path, job_id


def test_smoke_assemble_produces_valid_pdf_with_keywords(
    seeded_db_and_runs_dir: tuple[sqlite3.Connection, Path, int],
) -> None:
    conn, tmp_path, job_id = seeded_db_and_runs_dir

    vocab = sorted(
        set(
            w
            for src in [
                # bullets
                "Built ETL pipelines processing 30M rows per day in Python.",
                "Operated Kubernetes clusters across three regions.",
                "Mentored two junior engineers on ML systems.",
                "Shipped a Rails monolith and wrote ad hoc PHP utilities.",
                "Wrote SQL ETL jobs for the analytics team.",
                # requirements
                "Build and operate data pipelines. pipelines etl",
                "Operate Kubernetes clusters in production. kubernetes k8s",
                "Mentor engineers. mentor",
            ]
            for w in tokenize(src)
        )
    )
    embedder = FakeEmbedder(vocab=vocab)

    result = assemble_one(
        conn=conn,
        run_id="2026-05-22-001",
        job_id=job_id,
        palette="slate",
        font="atkinson-hyperlegible",
        embedder=embedder,
        # FakeEmbedder is bag-of-words; real bge clears 0.6 easily but
        # synthetic vectors top out around 0.4 for paraphrases. Loosen
        # the floor here so we are testing the assembly path, not the
        # toy embedder's calibration.
        coverage_floor=0.3,
    )

    # PDF is non-empty
    assert result.cv_path.exists()
    assert result.cv_path.stat().st_size > 2000, "PDF looks suspiciously small"

    # Extracted text contains the must-have keywords we required
    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(result.cv_path)).pages)
    text_l = text.lower()
    assert "kubernetes" in text_l, f"Kubernetes missing from rendered PDF text. Got:\n{text}"
    assert "pipelines" in text_l or "etl" in text_l, f"pipelines/etl missing. Got:\n{text}"

    # Personal details made it through
    assert "Shiva Padakanti" in text
    assert "Anthropic" not in text  # company name only on the JD side, not the CV
    assert "Modal" in text  # but our employer is on the CV

    # Coverage report exists and reflects coverage of both must-haves
    coverage = json.loads(result.coverage_report_path.read_text())
    must_haves = coverage["semantic"]["must_haves"]
    assert len(must_haves) == 2
    covered_count = sum(1 for r in must_haves if r["covered"])
    assert covered_count >= 1

    # ATS keyword presence: the rendered text should literally contain
    # 'kubernetes' (we picked a Kubernetes bullet)
    kp = coverage["keyword_presence"]
    kp_by_text = {r["requirement"]: r for r in kp}
    assert kp_by_text["Operate Kubernetes clusters in production."]["present"] is True

    # Selectivity is tested in test_matching.py against the pure select_
    # components() function. Here we only verify the assembly path end to
    # end: a non-empty, well-formed PDF whose text contains the keywords
    # the JD required. That is the M5 mandatory check.

    # cv.json shape sanity
    cv_json = json.loads(result.cv_json_path.read_text())
    assert cv_json["schema_version"] == 1
    assert cv_json["profile"]["name"] == "Shiva Padakanti"
    assert len(cv_json["experiences"]) >= 1


def test_smoke_fails_loud_when_no_verified_bullets(tmp_path: Path) -> None:
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    # Job has requirements but library is empty / no verified bullets.
    conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status, requirements_json) "
        "VALUES (?, ?, ?, ?, 'selected', ?)",
        (
            "X",
            "Y",
            "https://x/1",
            "JD",
            json.dumps(
                {
                    "schema_version": 1,
                    "job_id": 1,
                    "model_version": "t",
                    "requirements": [{"type": "must-have", "text": "x", "keywords": []}],
                }
            ),
        ),
    )
    with pytest.raises(RuntimeError) as exc:
        assemble_one(
            conn=conn,
            run_id="r",
            job_id=1,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(vocab=["x"]),
        )
    assert "verified" in str(exc.value).lower()


def test_smoke_fails_loud_when_requirements_missing(tmp_path: Path) -> None:
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    exp = lib.add_experience(conn, company="C", role="R")
    lib.add_bullet(conn, experience_id=exp.id, text="Did stuff with Python.", facts_verified=True)
    conn.execute(
        "INSERT INTO job (company, title, url, jd_text, status) VALUES (?, ?, ?, ?, 'selected')",
        ("Anthropic", "FDE", "https://x/2", "JD"),
    )
    with pytest.raises(RuntimeError) as exc:
        assemble_one(
            conn=conn,
            run_id="r",
            job_id=1,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(vocab=["did", "python"]),
        )
    assert "requirements" in str(exc.value).lower()
