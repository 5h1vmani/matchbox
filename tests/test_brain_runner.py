"""Brain runner tests: ingest + tailor over injected fake Completers.

No real network. A `Completer` is just `(system, user) -> str`, so each test
hands the runner a callable that returns canned JSON. These prove the runner's
contract: valid output lands through the deterministic core (rows unverified for
ingest; a rendered cv.pdf + a schema-valid status.json for tailor), the schema
retry path recovers from one bad reply, and two bad replies fail loud.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from matchbox.brain.llm import BrainError
from matchbox.brain.runner import run_ingest, run_tailor
from matchbox.contracts import Status, schema_errors
from matchbox.core import library as lib
from matchbox.core.db import connect
from matchbox.core.migrations import migrate
from matchbox.matching.bm25 import tokenize


@dataclass(slots=True)
class FakeEmbedder:
    """Bag-of-words embedder -- deterministic, no network (same as the smoke
    test's)."""

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


def _noop_progress(step: str, detail: str) -> None:
    """Progress sink for tests -- the runner's events are not asserted here."""


class ScriptedCompleter:
    """Returns the next canned reply on each call, ignoring the prompt.

    Lets a test script the exact sequence the runner will pull (requirements,
    then selection, then -- only if reached -- polish), and assert how many calls
    happened."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._replies:
            raise AssertionError("ScriptedCompleter ran out of replies")
        return self._replies.pop(0)


# ── ingest ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "matchbox.db")
    migrate(c)
    return c


def _valid_ingest_json() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "experiences": [
                {
                    "company": "Acme",
                    "role": "Engineer",
                    "start_date": "2022-01",
                    "bullets": [
                        {
                            "text": "Built ETL pipelines processing 30M rows per day.",
                            "has_metric": True,
                            "source_file": "cv.txt",
                        }
                    ],
                }
            ],
            "skills": [{"name": "Python", "category": "Languages"}],
        }
    )


def test_run_ingest_happy_path_lands_unverified(conn: sqlite3.Connection, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "cv.txt").write_text("Engineer at Acme. Built ETL pipelines.", encoding="utf-8")

    complete = ScriptedCompleter([_valid_ingest_json()])
    counts = run_ingest(conn, "demo", complete, _noop_progress, inbox_dir=inbox)

    assert counts["bullets"] == 1
    assert counts["experiences"] == 1
    # Rows land unverified -- the honesty lever survives the in-app path.
    rows = conn.execute("SELECT facts_verified FROM bullet").fetchall()
    assert rows and all(r["facts_verified"] == 0 for r in rows)


def test_run_ingest_retries_once_then_succeeds(conn: sqlite3.Connection, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "cv.txt").write_text("notes", encoding="utf-8")

    # First reply is invalid (missing schema_version); second is valid.
    bad = json.dumps({"experiences": []})
    complete = ScriptedCompleter([bad, _valid_ingest_json()])
    counts = run_ingest(conn, "demo", complete, _noop_progress, inbox_dir=inbox)

    assert counts["bullets"] == 1
    assert len(complete.calls) == 2  # retried exactly once
    # The retry prompt carried the validation error back to the model.
    assert "rejected" in complete.calls[1][1].lower()


def test_run_ingest_hard_fails_after_two_bad_replies(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "cv.txt").write_text("notes", encoding="utf-8")

    bad = json.dumps({"experiences": []})
    complete = ScriptedCompleter([bad, bad])
    with pytest.raises(BrainError) as exc:
        run_ingest(conn, "demo", complete, _noop_progress, inbox_dir=inbox)
    assert "ingest.v1.json" in str(exc.value)
    assert len(complete.calls) == 2


def test_run_ingest_empty_inbox_fails_loud(conn: sqlite3.Connection, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    complete = ScriptedCompleter([_valid_ingest_json()])
    with pytest.raises(BrainError):
        run_ingest(conn, "demo", complete, _noop_progress, inbox_dir=inbox)


# ── tailor ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[sqlite3.Connection, int, FakeEmbedder, tuple[int, int]]:
    """A library + a job, with runs/ pointed at tmp_path.

    Mirrors test_assemble_smoke's fixture, but also patches scoring.runs.RUNS_DIR
    (create_run) and assemble.RUNS_DIR (assemble_one output) to the SAME tmp dir,
    since run_tailor exercises both. Requirements are NOT pre-seeded -- the brain
    extracts them as step one."""
    conn = connect(tmp_path / "matchbox.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO profile (full_name, email, location, links_json, headline) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Shiva Padakanti", "shiva@example.com", "Remote", "[]", "Generalist engineer"),
    )
    exp = lib.add_experience(
        conn, company="Modal", role="Forward Deployed Engineer", start_date="2024-01"
    )
    b1 = lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Built ETL pipelines processing 30M rows per day in Python.",
        has_metric=True,
        facts_verified=True,
    )
    b2 = lib.add_bullet(
        conn,
        experience_id=exp.id,
        text="Operated Kubernetes clusters across three regions.",
        facts_verified=True,
    )
    cur = conn.execute(
        "INSERT INTO job (company, title, url, jd_text, apply_url, location, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'selected')",
        (
            "Anthropic",
            "Forward Deployed Engineer",
            "https://job.example/fde",
            "We need someone to build ETL pipelines and operate Kubernetes in production.",
            "https://apply.example/fde",
            "Remote",
        ),
    )
    assert cur.lastrowid is not None
    job_id = cur.lastrowid

    from matchbox import assemble as assemble_mod
    from matchbox.scoring import runs as runs_mod

    monkeypatch.setattr(assemble_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runs_mod, "RUNS_DIR", tmp_path / "runs")
    (tmp_path / "runs").mkdir(exist_ok=True)

    vocab = sorted(
        {
            w
            for src in [
                "Built ETL pipelines processing 30M rows per day in Python.",
                "Operated Kubernetes clusters across three regions.",
                "Build and operate data pipelines. pipelines etl",
                "Operate Kubernetes clusters in production. kubernetes k8s",
            ]
            for w in tokenize(src)
        }
    )
    # The bullet ids are returned for the scripted selection replies.
    return conn, job_id, FakeEmbedder(vocab=vocab), (b1.id, b2.id)


def test_run_tailor_end_to_end(
    seeded: tuple[sqlite3.Connection, int, FakeEmbedder, tuple[int, int]],
    tmp_path: Path,
) -> None:
    conn, job_id, embedder, (b1_id, b2_id) = seeded

    # Requirements whose keywords ARE present in the chosen bullet texts, so the
    # keyword-presence check passes and polish is never triggered (the simplest
    # end-to-end path, per the spec).
    reqs = json.dumps(
        {
            "schema_version": 1,
            "job_id": job_id,
            "model_version": "brain-byok-v1",
            "requirements": [
                {
                    "type": "must-have",
                    "text": "Build and operate data pipelines.",
                    "keywords": ["pipelines"],
                    "variants": [],
                },
                {
                    "type": "must-have",
                    "text": "Operate Kubernetes clusters in production.",
                    "keywords": ["kubernetes"],
                    "variants": ["k8s"],
                },
            ],
        }
    )
    selection = json.dumps(
        {
            "schema_version": 1,
            "run_id": "PLACEHOLDER",  # the runner injects the real run_id
            "job_id": job_id,
            "selected_bullet_ids": [b1_id, b2_id],
            "summary": (
                "Infrastructure engineer who builds data pipelines and operates "
                "Kubernetes in production, shipping reliable systems and mentoring "
                "the engineers around me every single week of the year."
            ),
        }
    )
    complete = ScriptedCompleter([reqs, selection])

    result = run_tailor(conn, "demo", job_id, complete, _noop_progress, embedder=embedder)

    # Only requirements + selection were needed; polish was skipped.
    assert len(complete.calls) == 2
    assert result["polish_applied"] == 0

    run_id = result["run_id"]
    cv_pdf = tmp_path / "runs" / run_id / "output" / str(job_id) / "cv.pdf"
    assert cv_pdf.exists()
    assert cv_pdf.stat().st_size > 2000

    # status.json exists and validates against the Status model + its schema.
    status_path = tmp_path / "runs" / run_id / "status.json"
    assert status_path.exists()
    status_doc = json.loads(status_path.read_text())
    assert schema_errors("status.v1.json", status_doc) == []
    parsed = Status.model_validate(status_doc)
    assert parsed.status == "done"
    assert parsed.jobs[0].cv_status == "done"
    assert parsed.jobs[0].cv_path is not None


def test_run_tailor_retries_selection_on_unverified_id(
    seeded: tuple[sqlite3.Connection, int, FakeEmbedder, tuple[int, int]],
) -> None:
    """A selection naming an unknown id is rejected by assemble_one; the runner
    feeds the error back and the second selection (valid) renders."""
    conn, job_id, embedder, (b1_id, b2_id) = seeded
    reqs = json.dumps(
        {
            "schema_version": 1,
            "job_id": job_id,
            "model_version": "brain-byok-v1",
            "requirements": [
                {
                    "type": "must-have",
                    "text": "Build and operate data pipelines.",
                    "keywords": ["pipelines"],
                    "variants": [],
                },
                {
                    "type": "must-have",
                    "text": "Operate Kubernetes clusters in production.",
                    "keywords": ["kubernetes"],
                    "variants": ["k8s"],
                },
            ],
        }
    )
    summary = (
        "Infrastructure engineer who builds data pipelines and operates Kubernetes "
        "in production, shipping reliable systems and mentoring the engineers around "
        "me every single week of the year."
    )
    bad_sel = json.dumps(
        {
            "schema_version": 1,
            "run_id": "PLACEHOLDER",
            "job_id": job_id,
            "selected_bullet_ids": [b1_id, 9999],  # 9999 is not a verified bullet
            "summary": summary,
        }
    )
    good_sel = json.dumps(
        {
            "schema_version": 1,
            "run_id": "PLACEHOLDER",
            "job_id": job_id,
            "selected_bullet_ids": [b1_id, b2_id],
            "summary": summary,
        }
    )
    complete = ScriptedCompleter([reqs, bad_sel, good_sel])
    result = run_tailor(conn, "demo", job_id, complete, _noop_progress, embedder=embedder)
    # requirements + bad selection + good selection.
    assert len(complete.calls) == 3
    assert result["run_id"]


def test_run_tailor_missing_job_fails_loud(
    seeded: tuple[sqlite3.Connection, int, FakeEmbedder, tuple[int, int]],
) -> None:
    conn, _job_id, embedder, _ids = seeded
    complete = ScriptedCompleter([])
    with pytest.raises(BrainError) as exc:
        run_tailor(conn, "demo", 9999, complete, _noop_progress, embedder=embedder)
    assert "9999" in str(exc.value)
