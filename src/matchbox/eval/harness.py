"""Run scoring + selection over a labeled golden corpus, report metrics.

The harness is the measurement instrument the product thesis calls for
("eval harness first"): it exercises the *unchanged* production scoring
(``matchbox.scoring.rubric.score_job``) and selection
(``matchbox.matching.select.select_components``) against a hand-labeled
corpus and reports how well they rank and cover.

Design constraints honored here:

* It never touches the database and never renders a document. The corpus
  is plain JSON; embeddings are computed in memory via an injected
  :class:`~matchbox.matching.embed.Embedder`.
* It is compatible with ``score_job``'s keyword-only signature. The
  ``semantic_fit`` value is computed by the harness from a profile
  centroid built from the candidate's bullets and skills, mirroring
  ``rubric._profile_centroid`` (mean of L2-normalized embeddings).
* Offline by default for tests: callers inject a deterministic fake
  embedder. The CLI path uses the real ``FastEmbedEmbedder`` unless
  ``MATCHBOX_DISABLE_SEMANTIC`` is set, exactly like the web scoring
  route.

The output is a flat ``dict[str, float]`` of metrics plus a small amount
of structured detail, which :func:`format_report` renders as a table.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from matchbox.eval.metrics import (
    keyword_recall,
    mrr,
    ndcg_at_k,
    precision_at_k,
    requirement_coverage_rate,
)
from matchbox.matching.coverage import check_keyword_presence
from matchbox.matching.embed import Embedder, cosine
from matchbox.matching.select import (
    Component,
    Requirement,
    SelectionResult,
    select_components,
)
from matchbox.scoring.rubric import JobScore, score_job

DEFAULT_CORPUS = Path(__file__).resolve().parent / "corpus" / "baseline.json"

# A job is "relevant" (binary) for precision/MRR when its graded label is
# at least this value. Graded labels are 0/1/2; 1 = adjacent, 2 = strong.
RELEVANT_THRESHOLD = 1

# Selection cases are synthetic and the candidate phrasings are
# paraphrases of the requirements, so the bag-of-words FakeEmbedder tops
# out well below the production bge floor (0.5). The harness therefore
# uses a lower coverage floor, mirroring the choice made in
# tests/test_assemble_smoke.py, so we measure the selection logic rather
# than the toy embedder's calibration. The CLI exposes --coverage-floor
# to evaluate against the production floor with a real embedder.
DEFAULT_COVERAGE_FLOOR = 0.3


# ─── corpus model ─────────────────────────────────────────────────────


@dataclass(slots=True)
class CandidateBullet:
    text: str
    has_metric: bool = False


@dataclass(slots=True)
class Candidate:
    target: dict[str, list[str]]
    skills: list[str]
    bullets: list[CandidateBullet]


@dataclass(slots=True)
class ScoringCase:
    id: str
    relevance: int
    job: dict[str, Any]


@dataclass(slots=True)
class SelectionCase:
    id: str
    requirements: list[Requirement]
    # 0-based requirement index (over must-haves, in declaration order) ->
    # the 0-based candidate-bullet indices that should cover it.
    expected_cover_bullets: dict[int, list[int]]


@dataclass(slots=True)
class Corpus:
    candidate: Candidate
    scoring_cases: list[ScoringCase]
    selection_cases: list[SelectionCase]


def _coerce_target(raw: dict[str, Any]) -> dict[str, list[str]]:
    """Normalize the candidate target into the shape ``score_job`` expects,
    tolerating missing keys."""
    keys = ("role_families", "dream_companies", "locations", "exclusions")
    return {k: [str(x) for x in raw.get(k, [])] for k in keys}


def load_corpus(path: Path | str = DEFAULT_CORPUS) -> Corpus:
    """Parse a corpus JSON file into typed dataclasses.

    Raises ``ValueError`` on a structurally invalid corpus so a typo in
    the golden file fails loud rather than silently scoring nothing.
    """
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))

    cand_raw = data.get("candidate")
    if not isinstance(cand_raw, dict):
        raise ValueError("corpus is missing a 'candidate' object")
    bullets = [
        CandidateBullet(text=str(b["text"]), has_metric=bool(b.get("has_metric", False)))
        for b in cand_raw.get("bullets", [])
    ]
    candidate = Candidate(
        target=_coerce_target(cand_raw.get("target", {})),
        skills=[str(s) for s in cand_raw.get("skills", [])],
        bullets=bullets,
    )

    scoring_cases = [
        ScoringCase(id=str(c["id"]), relevance=int(c["relevance"]), job=dict(c["job"]))
        for c in data.get("scoring_cases", [])
    ]

    selection_cases: list[SelectionCase] = []
    for c in data.get("selection_cases", []):
        reqs = [
            Requirement(
                text=str(r["text"]),
                type=str(r["type"]),
                keywords=[str(k) for k in r.get("keywords", [])],
                variants=[str(v) for v in r.get("variants", [])],
            )
            for r in c.get("requirements", [])
        ]
        expected = {
            int(k): [int(i) for i in v]
            for k, v in dict(c.get("expected_cover_bullets", {})).items()
        }
        selection_cases.append(
            SelectionCase(id=str(c["id"]), requirements=reqs, expected_cover_bullets=expected)
        )

    if not scoring_cases and not selection_cases:
        raise ValueError("corpus has neither scoring_cases nor selection_cases")
    return Corpus(candidate=candidate, scoring_cases=scoring_cases, selection_cases=selection_cases)


# ─── embedding helpers ────────────────────────────────────────────────


def _encode_one(embedder: Embedder, text: str) -> np.ndarray:
    return embedder.encode([text])[0]


def build_profile_centroid(embedder: Embedder, candidate: Candidate) -> np.ndarray | None:
    """Mean of the L2-normalized embeddings of the candidate's bullets and
    skills — the same construction as ``rubric._profile_centroid``, but in
    memory over the corpus instead of over the DB. Returns ``None`` when
    the candidate has no bullets or skills.
    """
    texts = [b.text for b in candidate.bullets] + list(candidate.skills)
    if not texts:
        return None
    vecs = embedder.encode(texts)
    normed = [v / max(float(np.linalg.norm(v)), 1e-12) for v in vecs]
    if not normed:
        return None
    centroid: np.ndarray = np.vstack(normed).mean(axis=0)
    return centroid


def _user_tech_tokens(candidate: Candidate) -> set[str]:
    """Lowercased token set of the candidate's skills — the corpus analogue
    of ``rubric._user_tech_tokens`` (which reads skills + tech tags from
    the DB; the corpus only carries skills)."""
    from matchbox.core.text import tokenize

    tokens: set[str] = set()
    for skill in candidate.skills:
        tokens.update(tokenize(skill))
    return tokens


# ─── scoring evaluation ───────────────────────────────────────────────


@dataclass(slots=True)
class ScoredCase:
    id: str
    relevance: int
    total: float
    semantic_fit: float | None


def score_corpus(
    corpus: Corpus, embedder: Embedder | None
) -> tuple[list[ScoredCase], dict[str, float]]:
    """Score every scoring case and rank by predicted total descending.

    Returns the ranked cases and the ranking-quality metrics. When
    ``embedder`` is ``None`` the semantic dimension is omitted (``score_job``
    renormalizes the remaining weights), so the harness still measures the
    lexical-only ranking.
    """
    centroid = build_profile_centroid(embedder, corpus.candidate) if embedder else None
    tech_tokens = _user_tech_tokens(corpus.candidate)

    scored: list[ScoredCase] = []
    for case in corpus.scoring_cases:
        semantic_fit: float | None = None
        if embedder is not None and centroid is not None and case.job.get("jd_text"):
            jd_vec = _encode_one(embedder, str(case.job["jd_text"]))
            semantic_fit = cosine(centroid, jd_vec)
        result: JobScore = score_job(
            job=case.job,
            target=corpus.candidate.target,
            user_tech_tokens=tech_tokens,
            semantic_fit=semantic_fit,
        )
        scored.append(
            ScoredCase(
                id=case.id,
                relevance=case.relevance,
                total=result.total,
                semantic_fit=semantic_fit,
            )
        )

    # Rank by predicted score, descending. Ties broken by id for a stable,
    # reproducible ordering across runs and platforms.
    ranked = sorted(scored, key=lambda s: (-s.total, s.id))

    graded = [float(s.relevance) for s in ranked]
    labels = [s.relevance >= RELEVANT_THRESHOLD for s in ranked]
    k = len(ranked)
    metrics = {
        "scoring_cases": float(k),
        "ndcg_at_k": ndcg_at_k(graded, k),
        "ndcg_at_3": ndcg_at_k(graded, 3),
        "precision_at_3": precision_at_k(labels, 3),
        "mrr": mrr(labels),
    }
    return ranked, metrics


# ─── selection evaluation ─────────────────────────────────────────────


@dataclass(slots=True)
class SelectionCaseResult:
    id: str
    coverage_rate: float
    expected_bullets_selected_rate: float
    keyword_recall: float


def _components_for(candidate: Candidate) -> list[Component]:
    """Each candidate bullet becomes a selectable Component. Index in the
    list == the ``id`` so the corpus' bullet indices line up with selected
    ids. All from one experience: the corpus tests coverage, not the
    per-role cap (which has its own unit test)."""
    return [
        Component(id=i, text=b.text, experience_id=0, has_metric=b.has_metric)
        for i, b in enumerate(candidate.bullets)
    ]


def evaluate_selection_case(
    case: SelectionCase,
    components: list[Component],
    embedder: Embedder,
    *,
    coverage_floor: float,
) -> SelectionCaseResult:
    """Run ``select_components`` for one case and measure coverage, whether
    the *expected* bullets were chosen, and keyword recall of the selected
    text."""
    comp_vecs = embedder.encode([c.text for c in components])
    req_vecs = embedder.encode([_req_query(r) for r in case.requirements])

    n_must = sum(1 for r in case.requirements if r.type == "must-have")
    result: SelectionResult = select_components(
        components=components,
        component_embeddings=comp_vecs,
        requirements=case.requirements,
        requirement_embeddings=req_vecs,
        # Ask for at least every must-have plus a little headroom so the
        # selection is not starved below what coverage needs.
        k=max(n_must + 2, len(components)),
        per_role_cap=len(components),
        coverage_floor=coverage_floor,
    )

    coverage_rate = requirement_coverage_rate(result.covered)
    selected = set(result.selected_ids)

    # Did the hand-labeled "this bullet should cover requirement j" bullets
    # actually get selected? Averaged over the labeled must-haves.
    expected_hits = 0
    expected_total = 0
    for wanted in case.expected_cover_bullets.values():
        if not wanted:
            continue
        expected_total += 1
        if any(idx in selected for idx in wanted):
            expected_hits += 1
    expected_rate = expected_hits / expected_total if expected_total else 0.0

    # Keyword recall: of every must-have keyword, how many survive into the
    # selected bullet text? Uses the production keyword-presence check.
    selected_text = "\n".join(c.text for c in components if c.id in selected)
    must_haves = [r for r in case.requirements if r.type == "must-have"]
    required_kw = [kw for r in must_haves for kw in (r.keywords or [r.text])]
    presence = check_keyword_presence(selected_text, must_haves)
    present_kw = [p.matched_term for p in presence if p.present and p.matched_term]
    kw_recall = keyword_recall(required_kw, present_kw)

    return SelectionCaseResult(
        id=case.id,
        coverage_rate=coverage_rate,
        expected_bullets_selected_rate=expected_rate,
        keyword_recall=kw_recall,
    )


def _req_query(r: Requirement) -> str:
    """Mirror ``select._query_for_requirement`` for embedding the
    requirement (text + keywords + variants) — kept local so the harness
    does not depend on a private helper."""
    parts = [r.text, *r.keywords, *r.variants]
    return " ".join(p for p in parts if p)


def select_corpus(
    corpus: Corpus, embedder: Embedder, *, coverage_floor: float = DEFAULT_COVERAGE_FLOOR
) -> tuple[list[SelectionCaseResult], dict[str, float]]:
    """Evaluate every selection case and average the metrics.

    Selection requires real embeddings, so ``embedder`` is non-optional
    here (a fake embedder is fine).
    """
    components = _components_for(corpus.candidate)
    results = [
        evaluate_selection_case(c, components, embedder, coverage_floor=coverage_floor)
        for c in corpus.selection_cases
    ]
    if not results:
        return [], {
            "selection_cases": 0.0,
            "mean_requirement_coverage": 0.0,
            "mean_expected_bullets_selected": 0.0,
            "mean_keyword_recall": 0.0,
        }
    metrics = {
        "selection_cases": float(len(results)),
        "mean_requirement_coverage": _mean(r.coverage_rate for r in results),
        "mean_expected_bullets_selected": _mean(r.expected_bullets_selected_rate for r in results),
        "mean_keyword_recall": _mean(r.keyword_recall for r in results),
    }
    return results, metrics


def _mean(values: Any) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


# ─── top-level run ────────────────────────────────────────────────────


@dataclass(slots=True)
class EvalReport:
    metrics: dict[str, float]
    scored: list[ScoredCase] = field(default_factory=list)
    selection: list[SelectionCaseResult] = field(default_factory=list)


def run_eval(
    corpus: Corpus,
    embedder: Embedder | None,
    *,
    coverage_floor: float = DEFAULT_COVERAGE_FLOOR,
) -> EvalReport:
    """Run both halves and merge the metrics.

    ``embedder`` may be ``None`` to evaluate lexical-only scoring; in that
    case selection (which needs embeddings) is skipped and its metrics are
    reported as ``0.0`` with a ``selection_cases`` count of 0.
    """
    scored, scoring_metrics = score_corpus(corpus, embedder)
    if embedder is not None:
        selection, selection_metrics = select_corpus(
            corpus, embedder, coverage_floor=coverage_floor
        )
    else:
        selection = []
        _, selection_metrics = (
            [],
            {
                "selection_cases": 0.0,
                "mean_requirement_coverage": 0.0,
                "mean_expected_bullets_selected": 0.0,
                "mean_keyword_recall": 0.0,
            },
        )
    metrics = {**scoring_metrics, **selection_metrics}
    return EvalReport(metrics=metrics, scored=scored, selection=selection)


# ─── reporting ────────────────────────────────────────────────────────

_SCORING_KEYS = ("scoring_cases", "ndcg_at_k", "ndcg_at_3", "precision_at_3", "mrr")
_SELECTION_KEYS = (
    "selection_cases",
    "mean_requirement_coverage",
    "mean_expected_bullets_selected",
    "mean_keyword_recall",
)


def format_report(report: EvalReport, *, embedder_name: str) -> str:
    """Render a human-readable metrics table."""
    lines: list[str] = []
    lines.append("Matchbox eval harness")
    lines.append(f"  embedder: {embedder_name}")
    lines.append("")
    lines.append("Scoring (ranking quality)")
    for key in _SCORING_KEYS:
        lines.append(f"  {key:<32} {report.metrics.get(key, 0.0):.4f}")
    if report.scored:
        lines.append("  ranked jobs (predicted -> true relevance):")
        for s in report.scored:
            fit = f"{s.semantic_fit:.3f}" if s.semantic_fit is not None else "  -  "
            lines.append(f"    {s.total:.4f}  rel={s.relevance}  sem={fit}  {s.id}")
    lines.append("")
    lines.append("Selection (coverage)")
    for key in _SELECTION_KEYS:
        lines.append(f"  {key:<32} {report.metrics.get(key, 0.0):.4f}")
    for sc in report.selection:
        lines.append(
            f"    {sc.id:<28} cover={sc.coverage_rate:.2f} "
            f"expected={sc.expected_bullets_selected_rate:.2f} "
            f"kw_recall={sc.keyword_recall:.2f}"
        )
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────


def _resolve_embedder() -> tuple[Embedder | None, str]:
    """Real embedder for the CLI, unless ``MATCHBOX_DISABLE_SEMANTIC`` is
    set (mirrors ``web/routes/inbox._scoring_embedder``). Falls back to
    ``None`` if fastembed cannot construct, so the CLI still runs lexical-
    only rather than crashing."""
    if os.environ.get("MATCHBOX_DISABLE_SEMANTIC"):
        return None, "disabled (MATCHBOX_DISABLE_SEMANTIC) — lexical only"
    try:
        from matchbox.matching.embed import FastEmbedEmbedder

        return FastEmbedEmbedder(), "FastEmbedEmbedder (bge-small-en-v1.5)"
    except Exception as exc:  # pragma: no cover - depends on optional model
        return None, f"unavailable ({exc.__class__.__name__}) — lexical only"


def main(argv: list[str] | None = None) -> int:
    """``python -m matchbox.eval.harness [corpus.json] [--coverage-floor F]``.

    Loads the corpus, runs the eval with a real embedder (or lexical-only
    if semantic is disabled/unavailable), prints the metrics table, and
    returns 0. Returns 2 on a corpus that cannot be loaded.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    coverage_floor = DEFAULT_COVERAGE_FLOOR
    corpus_path: Path = DEFAULT_CORPUS
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--coverage-floor":
            i += 1
            if i >= len(args):
                print("error: --coverage-floor needs a value", file=sys.stderr)
                return 2
            coverage_floor = float(args[i])
        elif a in ("-h", "--help"):
            print(main.__doc__)
            return 0
        else:
            corpus_path = Path(a)
        i += 1

    try:
        corpus = load_corpus(corpus_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not load corpus {corpus_path}: {exc}", file=sys.stderr)
        return 2

    embedder, name = _resolve_embedder()
    report = run_eval(corpus, embedder, coverage_floor=coverage_floor)
    print(format_report(report, embedder_name=name))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
