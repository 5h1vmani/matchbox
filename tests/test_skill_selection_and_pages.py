"""Tests for items 1-3: selected_skill_ids validation, deterministic skills
fallback, and target_pages bullet-budget scaling plus changes.md lines."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from matchbox.assemble import assemble_one
from matchbox.assemble_parts.cvdoc import _jd_matched_skills
from matchbox.assemble_parts.reporting import _write_changes_md
from matchbox.assemble_parts.selection import _apply_skill_selection
from matchbox.core import library as lib
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.matching.bm25 import tokenize

# ─── helpers ────────────────────────────────────────────────────────────────


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


def _vocab(*texts: str) -> list[str]:
    return sorted({w for t in texts for w in tokenize(t)})


@pytest.fixture()
def skill_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    return conn


@pytest.fixture()
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[sqlite3.Connection, Path, int]:
    """A DB with 3 verified bullets, 3 skills, 1 job."""
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    conn.execute("INSERT INTO profile (full_name, links_json) VALUES (?, ?)", ("Dev", "[]"))
    exp = lib.add_experience(conn, company="Corp", role="SWE", start_date="2022-01")
    lib.add_bullet(
        conn, experience_id=exp.id, text="Built ETL pipelines in Python.", facts_verified=True
    )
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Operated Kubernetes clusters across regions.",
        facts_verified=True,
    )
    lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Designed REST services using FastAPI.",
        facts_verified=True,
    )
    lib.add_skill(conn, name="Python", category="Languages")
    lib.add_skill(conn, name="Kubernetes", category="Infra")
    lib.add_skill(conn, name="FastAPI", category="Frameworks")

    reqs_json = json.dumps(
        {
            "schema_version": 1,
            "job_id": 1,
            "model_version": "t",
            "requirements": [
                {
                    "type": "must-have",
                    "text": "Build ETL pipelines.",
                    "keywords": ["etl", "pipelines"],
                    "variants": [],
                },
                {
                    "type": "must-have",
                    "text": "Operate Kubernetes.",
                    "keywords": ["kubernetes"],
                    "variants": [],
                },
            ],
        }
    )
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, status, requirements_json) "
        "VALUES (?, ?, ?, ?, ?, 'selected', ?)",
        (
            "Acme",
            "Engineer",
            "https://x/1",
            "We need someone who knows Python, Kubernetes and FastAPI.",
            "https://apply/1",
            reqs_json,
        ),
    )
    job_id = cur.lastrowid
    assert job_id is not None

    monkeypatch.setattr("matchbox.assemble.RUNS_DIR", tmp_path / "runs")
    return conn, tmp_path, int(job_id)


# ─── Item 1: selected_skill_ids validation ──────────────────────────────────


class TestApplySkillSelection:
    def test_unknown_id_raises(self, skill_db: sqlite3.Connection) -> None:
        lib.add_skill(skill_db, name="Python", category="Languages")
        with pytest.raises(ValueError, match="not library skills"):
            _apply_skill_selection(
                {"selected_skill_ids": [1, 9999]},
                {1: {"name": "Python", "category": "Languages"}},
            )

    def test_category_order_follows_brain_id_order(self, skill_db: sqlite3.Connection) -> None:
        s1 = lib.add_skill(skill_db, name="Python", category="Languages")
        s2 = lib.add_skill(skill_db, name="Kubernetes", category="Infra")
        s3 = lib.add_skill(skill_db, name="Postgres", category="Databases")
        library = {
            s1.id: {"name": "Python", "category": "Languages"},
            s2.id: {"name": "Kubernetes", "category": "Infra"},
            s3.id: {"name": "Postgres", "category": "Databases"},
        }
        # Brain lists Infra first, then Languages, then Databases.
        result = _apply_skill_selection(
            {"selected_skill_ids": [s2.id, s1.id, s3.id]},
            library,
        )
        cats = [g["category"] for g in result]
        assert cats == ["Infra", "Languages", "Databases"]

    def test_items_within_category_follow_brain_order(self, skill_db: sqlite3.Connection) -> None:
        s1 = lib.add_skill(skill_db, name="Go", category="Languages")
        s2 = lib.add_skill(skill_db, name="Python", category="Languages")
        s3 = lib.add_skill(skill_db, name="Rust", category="Languages")
        library = {
            s1.id: {"name": "Go", "category": "Languages"},
            s2.id: {"name": "Python", "category": "Languages"},
            s3.id: {"name": "Rust", "category": "Languages"},
        }
        # Brain wants Rust, Go, Python (reverse alphabetical).
        result = _apply_skill_selection(
            {"selected_skill_ids": [s3.id, s1.id, s2.id]},
            library,
        )
        assert result == [{"category": "Languages", "items": ["Rust", "Go", "Python"]}]

    def test_empty_selection_returns_empty(self, skill_db: sqlite3.Connection) -> None:
        result = _apply_skill_selection({}, {})
        assert result == []

    def test_deduplicates_repeated_ids(self, skill_db: sqlite3.Connection) -> None:
        s1 = lib.add_skill(skill_db, name="Python", category="Languages")
        library = {s1.id: {"name": "Python", "category": "Languages"}}
        result = _apply_skill_selection(
            {"selected_skill_ids": [s1.id, s1.id, s1.id]},
            library,
        )
        assert result == [{"category": "Languages", "items": ["Python"]}]


class TestSkillSelectionInAssembleOne:
    def test_selected_skill_ids_rendered_in_brain_order(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        conn, tmp_path, job_id = seeded
        skills_in_db = conn.execute("SELECT id, name, category FROM skill ORDER BY id").fetchall()
        # skill ids: s1=Python/Languages, s2=Kubernetes/Infra, s3=FastAPI/Frameworks
        skill_ids = [r["id"] for r in skills_in_db]
        s1, s2, s3 = skill_ids[0], skill_ids[1], skill_ids[2]

        bullet_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM bullet WHERE facts_verified=1 ORDER BY id"
            ).fetchall()
        ]

        summary = (
            "Infrastructure engineer who builds data pipelines and operates Kubernetes "
            "in production, shipping reliable systems and mentoring the engineers around "
            "the team every single week."
        )
        # Brain picks Infra (s2) first, then Languages (s1), then Frameworks (s3).
        result = assemble_one(
            conn=conn,
            run_id="2026-06-11-001",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Built ETL pipelines in Python.",
                    "Operated Kubernetes clusters across regions.",
                    "Designed REST services using FastAPI.",
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                )
            ),
            coverage_floor=0.1,
            selection={
                "schema_version": 1,
                "run_id": "2026-06-11-001",
                "job_id": job_id,
                "selected_bullet_ids": bullet_ids,
                "selected_skill_ids": [s2, s1, s3],  # Infra, Languages, Frameworks
                "summary": summary,
            },
        )
        cv = json.loads(result.cv_json_path.read_text())
        skill_cats = [s["category"] for s in cv["skills"]]
        assert skill_cats == ["Infra", "Languages", "Frameworks"]

    def test_unknown_skill_id_is_hard_failure(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        conn, tmp_path, job_id = seeded
        # 26 words — clears the voice-gate minimum of 20, no banned words.
        summary = (
            "Infrastructure engineer who builds data pipelines and operates Kubernetes "
            "in production, shipping reliable systems and mentoring the engineers around "
            "the team every single week."
        )
        bullet_id = conn.execute(
            "SELECT id FROM bullet WHERE facts_verified=1 ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        with pytest.raises(ValueError, match="not library skills"):
            assemble_one(
                conn=conn,
                run_id="r",
                job_id=job_id,
                palette="slate",
                font="source-serif",
                embedder=FakeEmbedder(vocab=_vocab("Built ETL pipelines in Python.")),
                coverage_floor=0.1,
                selection={
                    "schema_version": 1,
                    "run_id": "r",
                    "job_id": job_id,
                    "selected_bullet_ids": [bullet_id],
                    "selected_skill_ids": [99999],
                    "summary": summary,
                },
            )


# ─── Item 2: deterministic skills fallback ─────────────────────────────────


class TestJdMatchedSkills:
    def _make_conn(self, tmp_path: Path) -> sqlite3.Connection:
        conn = connect(tmp_path / "m.db")
        migrate(conn)
        return conn

    def test_jd_matched_filters_by_name(self, tmp_path: Path) -> None:
        conn = self._make_conn(tmp_path)
        lib.add_skill(conn, name="Python", category="Languages")
        lib.add_skill(conn, name="Kubernetes", category="Infra")
        lib.add_skill(conn, name="COBOL", category="Legacy")
        # Add enough extra skills so COBOL is not topped up into the result.
        for i in range(10):
            lib.add_skill(conn, name=f"Skill{i}", category="Extra")
        groups, line = _jd_matched_skills(conn, "We need Python and Kubernetes experience.")
        names = [n for g in groups for n in g["items"]]
        assert "Python" in names
        assert "Kubernetes" in names
        assert "COBOL" not in names
        assert "rendered (JD-matched)" in line

    def test_topup_to_min_when_few_match(self, tmp_path: Path) -> None:
        conn = self._make_conn(tmp_path)
        # Add 3 matching skills and 10 non-matching.
        for i in range(3):
            lib.add_skill(conn, name=f"Skill{i}", category="A")
        for i in range(10):
            lib.add_skill(conn, name=f"Nope{i}", category="B")
        # jd only mentions Skill0, Skill1, Skill2
        groups, _ = _jd_matched_skills(conn, "We want Skill0 Skill1 Skill2")
        all_rendered = [n for g in groups for n in g["items"]]
        # Should top up to at least 6 (min match threshold).
        assert len(all_rendered) >= 6

    def test_cap_at_18_items(self, tmp_path: Path) -> None:
        conn = self._make_conn(tmp_path)
        for i in range(30):
            lib.add_skill(conn, name=f"skill{i}", category="Cat")
        jd = " ".join(f"skill{i}" for i in range(30))
        groups, line = _jd_matched_skills(conn, jd)
        total = sum(len(g["items"]) for g in groups)
        assert total <= 18

    def test_cap_at_4_categories(self, tmp_path: Path) -> None:
        conn = self._make_conn(tmp_path)
        for cat in ["A", "B", "C", "D", "E"]:
            for i in range(4):
                lib.add_skill(conn, name=f"{cat}{i}", category=cat)
        jd = " ".join(f"{cat}{i}" for cat in ["A", "B", "C", "D", "E"] for i in range(4))
        groups, _ = _jd_matched_skills(conn, jd)
        assert len(groups) <= 4

    def test_no_skills_returns_empty(self, tmp_path: Path) -> None:
        conn = self._make_conn(tmp_path)
        groups, line = _jd_matched_skills(conn, "No skills in the DB yet.")
        assert groups == []
        assert "0 of 0" in line

    def test_changes_md_records_skills_line(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        conn, tmp_path, job_id = seeded
        result = assemble_one(
            conn=conn,
            run_id="2026-06-11-002",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Built ETL pipelines in Python.",
                    "Operated Kubernetes clusters across regions.",
                    "Designed REST services using FastAPI.",
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                )
            ),
            coverage_floor=0.1,
        )
        md = result.changes_md_path.read_text()
        assert "Skills:" in md
        assert "rendered" in md

    def test_deterministic_fallback_never_dumps_all_library_when_jd_present(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        """Even with 54 skills in the DB, only JD-relevant ones render."""
        conn, tmp_path, job_id = seeded
        # Add many extra skills that are NOT in the JD.
        for i in range(20):
            lib.add_skill(conn, name=f"Irrelevant{i}", category="Legacy")
        result = assemble_one(
            conn=conn,
            run_id="2026-06-11-003",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Built ETL pipelines in Python.",
                    "Operated Kubernetes clusters across regions.",
                    "Designed REST services using FastAPI.",
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                )
            ),
            coverage_floor=0.1,
        )
        cv = json.loads(result.cv_json_path.read_text())
        total_rendered = sum(len(g["items"]) for g in cv["skills"])
        total_in_db = conn.execute("SELECT COUNT(*) FROM skill").fetchone()[0]
        assert total_rendered < total_in_db


# ─── Item 3: target_pages bullet budget scaling ────────────────────────────


class TestTargetPages:
    def _make_long_summary(self) -> str:
        return (
            "Engineer with a decade of demonstrated delivery across distributed data platforms, "
            "cloud infrastructure, machine learning pipelines and site reliability disciplines, "
            "with clear evidence of senior technical scope at each stage."
        )

    def test_target_pages_2_doubles_word_budget(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        """With target_pages=2 the word budget is 2*DEFAULT_WORD_BUDGET; more
        bullets fit without being dropped."""
        conn, tmp_path, job_id = seeded
        # Add many extra verified bullets so the 1-page budget would drop some.
        exp = conn.execute("SELECT id FROM experience LIMIT 1").fetchone()["id"]
        extra_ids = []
        for i in range(20):
            b = lib.add_bullet(
                conn,
                experience_id=exp,
                text=f"Deployed microservices iteration {i} using Docker and orchestration tools.",
                facts_verified=True,
            )
            extra_ids.append(b.id)

        all_bullet_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM bullet WHERE facts_verified=1 ORDER BY id"
            ).fetchall()
        ]
        summary = self._make_long_summary()

        # 1-page run — some bullets will be dropped.
        result1 = assemble_one(
            conn=conn,
            run_id="2026-06-11-p1",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                    *(
                        f"Deployed microservices iteration {i} using Docker and orchestration tools."
                        for i in range(20)
                    ),
                )
            ),
            coverage_floor=0.1,
            selection={
                "schema_version": 1,
                "run_id": "2026-06-11-p1",
                "job_id": job_id,
                "selected_bullet_ids": all_bullet_ids,
                "target_pages": 1,
                "summary": summary,
            },
        )

        # 2-page run — more or equal bullets should fit.
        result2 = assemble_one(
            conn=conn,
            run_id="2026-06-11-p2",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                    *(
                        f"Deployed microservices iteration {i} using Docker and orchestration tools."
                        for i in range(20)
                    ),
                )
            ),
            coverage_floor=0.1,
            selection={
                "schema_version": 1,
                "run_id": "2026-06-11-p2",
                "job_id": job_id,
                "selected_bullet_ids": all_bullet_ids,
                "target_pages": 2,
                "summary": summary,
            },
        )

        assert len(result2.selected_component_ids) >= len(result1.selected_component_ids)

    def test_changes_md_pages_line_no_flag_when_within_target(self, tmp_path: Path) -> None:
        """When page_count <= target_pages, no 'exceeds target' flag."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path = _write_changes_md(
            out_dir=out_dir,
            job_company="Acme",
            job_title="Engineer",
            selected_ids=[],
            relevance={},
            raw_bullets={},
            semantic_gaps=[],
            keyword_presence=[],
            page_count=1,
            target_pages=1,
        )
        md = path.read_text()
        assert "Pages: 1 (target 1)" in md
        assert "exceeds target" not in md

    def test_changes_md_pages_line_flags_when_exceeds_target(self, tmp_path: Path) -> None:
        """When page_count > target_pages, the flag appears."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path = _write_changes_md(
            out_dir=out_dir,
            job_company="Acme",
            job_title="Engineer",
            selected_ids=[],
            relevance={},
            raw_bullets={},
            semantic_gaps=[],
            keyword_presence=[],
            page_count=2,
            target_pages=1,
        )
        md = path.read_text()
        assert "Pages: 2 (target 1)" in md
        assert "exceeds target" in md
        assert "target_pages: 2" in md

    def test_changes_md_pages_2_within_target_no_flag(self, tmp_path: Path) -> None:
        """target_pages=2, actual=2: no flag."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path = _write_changes_md(
            out_dir=out_dir,
            job_company="X",
            job_title="Y",
            selected_ids=[],
            relevance={},
            raw_bullets={},
            semantic_gaps=[],
            keyword_presence=[],
            page_count=2,
            target_pages=2,
        )
        md = path.read_text()
        assert "Pages: 2 (target 2)" in md
        assert "exceeds target" not in md

    def test_changes_md_skills_summary_line_appears(self, tmp_path: Path) -> None:
        """skills_summary_line is written into changes.md."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path = _write_changes_md(
            out_dir=out_dir,
            job_company="X",
            job_title="Y",
            selected_ids=[],
            relevance={},
            raw_bullets={},
            semantic_gaps=[],
            keyword_presence=[],
            skills_summary_line="Skills: 8 of 54 rendered (JD-matched)",
        )
        md = path.read_text()
        assert "Skills: 8 of 54 rendered (JD-matched)" in md

    def test_changes_md_brain_selected_skills_line(
        self, seeded: tuple[sqlite3.Connection, Path, int]
    ) -> None:
        conn, tmp_path, job_id = seeded
        skill_ids = [r["id"] for r in conn.execute("SELECT id FROM skill ORDER BY id").fetchall()]
        summary = self._make_long_summary()
        result = assemble_one(
            conn=conn,
            run_id="2026-06-11-sl",
            job_id=job_id,
            palette="slate",
            font="source-serif",
            embedder=FakeEmbedder(
                vocab=_vocab(
                    "Built ETL pipelines in Python.",
                    "Operated Kubernetes clusters across regions.",
                    "Designed REST services using FastAPI.",
                    "Build ETL pipelines. etl pipelines",
                    "Operate Kubernetes. kubernetes",
                )
            ),
            coverage_floor=0.1,
            selection={
                "schema_version": 1,
                "run_id": "2026-06-11-sl",
                "job_id": job_id,
                "selected_bullet_ids": [1, 2, 3],
                "selected_skill_ids": skill_ids,
                "summary": summary,
            },
        )
        md = result.changes_md_path.read_text()
        assert "Skills:" in md
        assert "brain-selected" in md
