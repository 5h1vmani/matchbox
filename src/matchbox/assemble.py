"""assemble — deterministic selection + HTML/weasyprint render for one job.

The brain invokes this once per job in a run:

    python -m matchbox.assemble --run <run_id> --job <job_id>
    python -m matchbox.assemble --run <run_id> --job <job_id> --selection sel.json
    python -m matchbox.assemble --run <run_id> --job <job_id> --cover

Selection is judgment, so the brain may make it: with --selection the brain
supplies the chosen verified-bullet ids (ordered) and a JD-tailored summary
(per schemas/selection.v1.json), and this module VALIDATES them -- every id
must be a real verified library bullet, the summary must pass the voice gate --
then renders. The no-fabrication guarantee lives in that validation, not in
selection being an algorithm.

Without --selection, the deterministic matcher picks (BM25 + embeddings + MMR);
that is the offline / no-key fallback, still reproducible and unit-testable.
The --cover form renders a cover letter from runs/<run>/output/<job>/cover.txt.

This module is the orchestrator. The loading, selection, coverage diagnostic,
CV-document building, changes.md reporting, and PDF-render helpers live under
matchbox.assemble_parts; they are imported here and the public names
(assemble_one, polish_run, drift_check, re_render_cv, assemble_cover,
validate_selection_payload, _palette_and_font_for) remain importable from this
module for existing callers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from matchbox.assemble_parts.cvdoc import _build_cv_json, _experiences_in_order, _pick_summary
from matchbox.assemble_parts.diagnostics import _requirement_synth_id, _semantic_coverage
from matchbox.assemble_parts.loaders import (
    _load_components,
    _load_job,
    _load_library_skills,
    _load_profile,
    _load_requirements,
    _load_unverified_bullets,
    _load_verified_projects,
)
from matchbox.assemble_parts.render import _extract_pdf_text, _palette_and_font_for, _render_pdf
from matchbox.assemble_parts.reporting import (
    _append_polish_section_to_changes_md,
    _write_changes_md,
)
from matchbox.assemble_parts.selection import (
    _apply_project_selection,
    _apply_selection,
    _apply_skill_selection,
    validate_selection_payload,
)
from matchbox.core.db import PROJECT_ROOT, connect
from matchbox.core.logging import configure_logging, get_logger
from matchbox.core.migrations import migrate
from matchbox.matching.coverage import check_keyword_presence
from matchbox.matching.embed import (
    DEFAULT_MODEL_VERSION,
    Embedder,
    FastEmbedEmbedder,
    cached_encode,
    cosine_matrix,
)
from matchbox.matching.select import SEMANTIC_COVERAGE_FLOOR, Requirement, select_components
from matchbox.polish import apply_polish, load_voice_rules, validate_polish_payload, validate_voice

# Public surface of this module. validate_selection_payload and
# _palette_and_font_for live in assemble_parts but are re-exported here because
# web routes and tests import them from matchbox.assemble; listing them keeps
# that contract explicit (and satisfies mypy's no-implicit-reexport).
__all__ = [
    "AssembleResult",
    "_palette_and_font_for",
    "assemble_cover",
    "assemble_one",
    "drift_check",
    "polish_run",
    "re_render_cv",
    "validate_selection_payload",
]

RUNS_DIR = PROJECT_ROOT / "runs"
DEFAULT_K = 12  # max bullets across all roles

log = get_logger(__name__)


@dataclass(slots=True)
class AssembleResult:
    cv_path: Path
    cv_json_path: Path
    coverage_report_path: Path
    changes_md_path: Path
    gaps: list[str]
    keyword_presence: list[dict[str, object]]
    selected_component_ids: list[int]


def assemble_one(
    *,
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
    embedder: Embedder | None = None,
    coverage_floor: float = SEMANTIC_COVERAGE_FLOOR,
    selection: dict[str, Any] | None = None,
) -> AssembleResult:
    """Selection + render path for a single job. Returns the artifact paths
    and the gaps / keyword-presence reports.

    `coverage_floor` defaults to the production value (0.5) tuned for
    bge-small-en-v1.5. Tests that use a weak FakeEmbedder pass a lower
    value explicitly.
    """
    log.info("assemble start run=%s job=%s", run_id, job_id)
    job_row = _load_job(conn, job_id)  # ensure the job exists; raises LookupError
    profile = _load_profile(conn)
    requirements = _load_requirements(conn, job_id)
    components, raw_bullets = _load_components(conn)

    if not components:
        raise RuntimeError(
            "no verified bullets in the library. Confirm components in /review first."
        )
    if not requirements:
        raise RuntimeError(f"job {job_id} has no extracted requirements. Run jobreqs save first.")

    embedder_inst = embedder or FastEmbedEmbedder(model_version=DEFAULT_MODEL_VERSION)

    # Embed components (cached) and requirements (also cached, with synthetic ids).
    comp_vecs_map = cached_encode(
        conn, embedder_inst, [("bullet", c.id, c.text) for c in components]
    )
    component_vecs = [comp_vecs_map[("bullet", c.id)] for c in components]

    # The dense embedding sees `text + keywords + variants` so a sparse
    # term that didn't make it into the requirement's prose still pulls
    # the vector toward components that contain it. Mirrors what
    # select._query_for_requirement does for BM25.
    def _req_blob(r: Requirement) -> str:
        return " ".join(p for p in [r.text, *r.keywords, *r.variants] if p)

    req_vecs_map = cached_encode(
        conn,
        embedder_inst,
        [
            ("requirement", _requirement_synth_id(job_id, i), _req_blob(r))
            for i, r in enumerate(requirements)
        ],
    )
    requirement_vecs = [
        req_vecs_map[("requirement", _requirement_synth_id(job_id, i))]
        for i, _ in enumerate(requirements)
    ]

    if selection is not None:
        # Brain-made selection (judgment). Validate ids against the verified
        # library and voice-gate the summary; the deterministic guarantee is the
        # validation, not the picking.
        selected_ids, relevance, summary_text = _apply_selection(selection, components)
        sim = (
            cosine_matrix(component_vecs, requirement_vecs)
            if requirements
            else np.zeros((len(components), 0), dtype=np.float32)
        )
    else:
        # Deterministic fallback (offline / no key): BM25 + embeddings + MMR.
        result = select_components(
            components=components,
            component_embeddings=component_vecs,
            requirements=requirements,
            requirement_embeddings=requirement_vecs,
            k=DEFAULT_K,
            per_role_cap=4,
            coverage_floor=coverage_floor,
        )
        selected_ids = result.selected_ids
        relevance = result.relevance_by_component
        sim = result.similarity_matrix
        summary_text = _pick_summary(conn)

    # Optional Projects section: brain-selected, verified projects only (the
    # deterministic fallback never picks projects).
    projects: list[dict[str, Any]] = []
    if selection is not None and selection.get("selected_project_ids"):
        projects = _apply_project_selection(selection, _load_verified_projects(conn))

    # Optional Skills section: brain-selected skill ids, or JD-filtered fallback.
    selected_skills: list[dict[str, Any]] | None = None
    if selection is not None and selection.get("selected_skill_ids"):
        selected_skills = _apply_skill_selection(selection, _load_library_skills(conn))

    # target_pages from selection (default 1 when no selection or not set).
    target_pages = int((selection or {}).get("target_pages") or 1)

    # Build the CV JSON, bullets in the chosen order (the brain's order when
    # supplied, library order otherwise).
    comp_by_id = {c.id: c for c in components}
    chosen = [comp_by_id[i] for i in selected_ids]
    experiences = _experiences_in_order(chosen, raw_bullets)
    jd_text: str | None = str(job_row.get("jd_text") or "") or None
    cv_json, skills_summary_line = _build_cv_json(
        profile=profile,
        experiences=experiences,
        summary_text=summary_text,
        conn=conn,
        projects=projects,
        selected_skills=selected_skills,
        jd_text=jd_text,
    )
    # Fingerprint the selected bullets so re_render_cv can warn when the
    # DB has drifted (the user edited a bullet after this render).
    cv_json["_selected_bullets"] = [{"id": c.id, "text_hash": _bullet_hash(c.text)} for c in chosen]

    if selection is not None and selection.get("headline"):
        headline = str(selection["headline"]).strip()
        hv = validate_voice(headline, load_voice_rules(), scope="headline")
        if hv:
            raise ValueError(
                "headline failed the voice gate: " + "; ".join(f"{v.rule}: {v.detail}" for v in hv)
            )
        cv_json["profile"]["headline"] = headline

    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_json_path = out_dir / "cv.json"
    cv_json_path.write_text(json.dumps(cv_json, indent=2), encoding="utf-8")

    cv_pdf_path = out_dir / "cv.pdf"
    page_count = _render_pdf(cv_json_path, cv_pdf_path, palette, font)

    # Coverage reports.
    pdf_text = _extract_pdf_text(cv_pdf_path)
    keyword_presence = check_keyword_presence(pdf_text, requirements)

    # Diagnostic-only: unverified bullets never enter the CV, but they let a
    # must-have read `partial` ("you have this, just not verified") instead of a
    # false gap. Embeddings are cached, so this is cheap on re-runs.
    unverified = _load_unverified_bullets(conn)
    unverified_sim: np.ndarray | None = None
    if unverified and requirement_vecs:
        unv_vecs_map = cached_encode(
            conn, embedder_inst, [("bullet", bid, text) for bid, text in unverified]
        )
        unv_vecs = [unv_vecs_map[("bullet", bid)] for bid, _ in unverified]
        unverified_sim = cosine_matrix(unv_vecs, requirement_vecs)

    must_haves, semantic_gaps = _semantic_coverage(
        requirements=requirements,
        components=components,
        selected_ids=selected_ids,
        similarity_matrix=sim,
        unverified=unverified,
        unverified_sim=unverified_sim,
        floor=coverage_floor,
    )

    coverage = {
        "semantic": {
            "floor": coverage_floor,
            "must_haves": must_haves,
            "gaps": semantic_gaps,
        },
        "keyword_presence": [
            {
                "requirement": kp.requirement_text,
                "matched_term": kp.matched_term,
                "present": kp.present,
            }
            for kp in keyword_presence
        ],
    }
    coverage_path = out_dir / "coverage.json"
    coverage_path.write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    changes_path = _write_changes_md(
        out_dir=out_dir,
        job_company=str(job_row["company"]),
        job_title=str(job_row["title"]),
        selected_ids=selected_ids,
        components=components,
        requirements=requirements,
        similarity_matrix=sim,
        relevance=relevance,
        raw_bullets=raw_bullets,
        semantic_gaps=semantic_gaps,
        keyword_presence=keyword_presence,
        page_count=page_count,
        target_pages=target_pages,
        skills_summary_line=skills_summary_line,
    )

    log.info(
        "assemble done run=%s job=%s selected=%d gaps=%d",
        run_id,
        job_id,
        len(selected_ids),
        len(semantic_gaps),
    )
    return AssembleResult(
        cv_path=cv_pdf_path,
        cv_json_path=cv_json_path,
        coverage_report_path=coverage_path,
        changes_md_path=changes_path,
        gaps=semantic_gaps,
        keyword_presence=[
            {"requirement": kp.requirement_text, "present": kp.present, "matched": kp.matched_term}
            for kp in keyword_presence
        ],
        selected_component_ids=selected_ids,
    )


# ─── polish path (rewording selected bullets, no re-selection) ────────


def polish_run(
    *,
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply a polish payload to an already-rendered run.

    Steps:
    1. Validate payload against schemas/polish.v1.json.
    2. Pull the existing coverage.json to find the bullet selected_ids.
    3. apply_polish() validates each polish against voice-rules.json,
       replaces bullet text in cv.json. Truthfulness is the brain's
       concern.
    4. Re-render cv.pdf from the updated cv.json.
    5. Re-run keyword-presence check on the new PDF text.
    6. Write a new coverage.json with the updated keyword presence;
       semantic coverage carries over unchanged.
    7. Append a "Polished" section to changes.md.

    Returns a summary dict suitable for stdout: {applied, rejected,
    keyword_presence_before, keyword_presence_after}.
    """
    log.info("polish start run=%s job=%s", run_id, job_id)
    errors = validate_polish_payload(payload)
    if errors:
        raise ValueError("polish.json failed schema validation: " + "; ".join(errors))
    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    coverage_path = out_dir / "coverage.json"
    if not coverage_path.exists():
        raise FileNotFoundError(f"no coverage.json at {coverage_path}. Run assemble first.")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))

    # selected_ids are not stored on disk; reconstruct from the DB
    # selected status flag, which assemble sets on run_job, or — easier
    # — re-run the matcher? No, that defeats the point. Persist
    # selected_ids in cv.json next time. For now, we load them from
    # run_job's job_id via the bullets that appear in cv.json:
    cv_json_path = out_dir / "cv.json"
    if not cv_json_path.exists():
        raise FileNotFoundError(f"no cv.json at {cv_json_path}. Run assemble first.")
    cv_json = json.loads(cv_json_path.read_text(encoding="utf-8"))
    # Find which DB bullet ids match the bullets in cv.json.
    bullets_in_cv = {b for exp in cv_json.get("experiences", []) for b in exp.get("bullets", [])}
    rows = conn.execute("SELECT id, text FROM bullet").fetchall()
    selected_ids = [r["id"] for r in rows if r["text"] in bullets_in_cv]
    # Plus any rows whose text appears as original_text in the payload —
    # this catches bullets already polished once.
    proposed_ids = {entry["id"] for entry in payload.get("polished", [])}
    selected_ids = sorted(set(selected_ids) | proposed_ids)

    applied, rejected, _new_cv = apply_polish(
        conn=conn,
        out_dir=out_dir,
        selected_ids=selected_ids,
        payload=payload,
    )

    keyword_presence_before = coverage.get("keyword_presence", [])

    if applied:
        # Re-render: cv.json was updated in place by apply_polish.
        _render_pdf(cv_json_path, out_dir / "cv.pdf", palette, font)

        # Re-run keyword presence on the new PDF text.
        pdf_text = _extract_pdf_text(out_dir / "cv.pdf")
        # Reconstruct Requirement objects from the cached job.requirements_json.
        requirements = _load_requirements(conn, job_id)
        keyword_presence_after = [
            {
                "requirement": kp.requirement_text,
                "matched_term": kp.matched_term,
                "present": kp.present,
            }
            for kp in check_keyword_presence(pdf_text, requirements)
        ]
        coverage["keyword_presence"] = keyword_presence_after
        coverage_path.write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    else:
        keyword_presence_after = keyword_presence_before

    _append_polish_section_to_changes_md(out_dir=out_dir, applied=applied, rejected=rejected)

    log.info(
        "polish done run=%s job=%s applied=%d rejected=%d",
        run_id,
        job_id,
        len(applied),
        len(rejected),
    )
    return {
        "applied": [{"id": bp.bullet_id, "new_text": bp.new_text} for bp in applied],
        "rejected": [
            {
                "id": bp.bullet_id,
                "violations": [{"rule": v.rule, "detail": v.detail} for v in bp.violations],
            }
            for bp in rejected
        ],
        "keyword_presence_before": keyword_presence_before,
        "keyword_presence_after": keyword_presence_after,
    }


# ─── re-render path (palette/font swap, no selection) ────────────────


def _bullet_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def drift_check(
    *,
    conn: sqlite3.Connection,
    cv_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare the fingerprints stored on cv.json against the live DB.

    Returns a list of drift records: {id, was_hash, now_hash, db_text}.
    Empty list means the cv.json reflects the current library.
    """
    fps = cv_json.get("_selected_bullets") or []
    if not fps:
        return []
    ids = [int(fp["id"]) for fp in fps]
    if not ids:
        return []
    rows = conn.execute(
        "SELECT id, text FROM bullet WHERE id IN ({})".format(",".join("?" * len(ids))),
        ids,
    ).fetchall()
    db_by_id = {r["id"]: r["text"] for r in rows}
    drift: list[dict[str, Any]] = []
    for fp in fps:
        bid = int(fp["id"])
        was = str(fp["text_hash"])
        live = db_by_id.get(bid)
        now = _bullet_hash(live) if live is not None else None
        if now != was:
            drift.append({"id": bid, "was_hash": was, "now_hash": now, "db_text": live})
    return drift


def re_render_cv(
    *,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
    conn: sqlite3.Connection | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Re-render a finished CV with a new palette/font.

    Returns (pdf_path, drift). `drift` is a list of bullets whose text
    in the DB no longer matches what cv.json says was selected. The
    caller decides whether to surface a warning. When `conn` is None
    the drift check is skipped (legacy callers that did not have a
    handy connection).
    """
    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    cv_json_path = out_dir / "cv.json"
    if not cv_json_path.exists():
        raise FileNotFoundError(f"cv.json not found for run {run_id}, job {job_id}. Tailor first.")
    cv_pdf_path = out_dir / "cv.pdf"
    _render_pdf(cv_json_path, cv_pdf_path, palette, font)
    drift: list[dict[str, Any]] = []
    if conn is not None:
        try:
            cv_json = json.loads(cv_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cv_pdf_path, drift
        drift = drift_check(conn=conn, cv_json=cv_json)
    return cv_pdf_path, drift


# ─── cover letter render ──────────────────────────────────────────────


def assemble_cover(
    *,
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
) -> Path:
    """Render cover.txt → cover.pdf via HTML + weasyprint.

    The brain writes cover.txt; this builds the profile/job metadata and
    calls render_cover_pdf, which produces a sibling cover.html and cover.pdf.
    """
    from matchbox.render_html import render_cover_pdf

    job = _load_job(conn, job_id)
    profile = _load_profile(conn)

    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    cover_txt = out_dir / "cover.txt"
    if not cover_txt.exists():
        raise FileNotFoundError(
            f"cover.txt missing at {cover_txt}. The brain writes the body; "
            "this renderer formats it."
        )

    contact: list[str] = []
    if profile.get("email"):
        contact.append(str(profile["email"]))
    if profile.get("phone"):
        contact.append(str(profile["phone"]))
    if profile.get("location"):
        contact.append(str(profile["location"]))
    contact.extend(json.loads(str(profile.get("links_json") or "[]")))

    cover_profile: dict[str, Any] = {
        "candidate_name": str(profile.get("full_name", "Your Name")),
        "contact": contact,
        "date": datetime.now(UTC).strftime("%B %d, %Y"),
        "recipient": ["Hiring Team", str(job["company"])],
        "salutation": "Dear Hiring Team,",
        "closing": "Sincerely,",
    }

    cover_pdf = out_dir / "cover.pdf"
    render_cover_pdf(cover_txt, cover_pdf, profile=cover_profile, palette=palette, font=font)
    return cover_pdf


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run id (YYYY-MM-DD-NNN)")
    parser.add_argument("--job", required=True, type=int, help="job id")
    parser.add_argument(
        "--cover",
        action="store_true",
        help="render the cover letter (reads cover.txt the brain wrote)",
    )
    parser.add_argument(
        "--polish",
        type=Path,
        default=None,
        metavar="POLISH_JSON",
        help="apply a polish payload (per schemas/polish.v1.json) to an already-rendered run",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=None,
        metavar="SELECTION_JSON",
        help="use the brain's chosen verified-bullet ids + summary "
        "(per schemas/selection.v1.json) instead of the deterministic matcher",
    )
    parser.add_argument("--db", type=Path, default=None, help="override DB path")
    args = parser.parse_args(argv)

    conn = connect(args.db) if args.db else connect()
    try:
        migrate(conn)
        palette, font = _palette_and_font_for(conn, args.run, args.job)

        if args.polish is not None:
            try:
                payload = json.loads(args.polish.read_text(encoding="utf-8"))
            except OSError as e:
                print(f"error: cannot read {args.polish}: {e}", file=sys.stderr)
                return 2
            except json.JSONDecodeError as e:
                print(f"error: invalid JSON in {args.polish}: {e}", file=sys.stderr)
                return 2
            try:
                summary = polish_run(
                    conn=conn,
                    run_id=args.run,
                    job_id=args.job,
                    palette=palette,
                    font=font,
                    payload=payload,
                )
            except FileNotFoundError as e:
                print(f"error: {e}", file=sys.stderr)
                return 5
            except ValueError as e:
                print(f"schema error: {e}", file=sys.stderr)
                return 3
            print(f"polish: applied {len(summary['applied'])}, rejected {len(summary['rejected'])}")
            for r in summary["rejected"]:
                print(f"  rejected bullet {r['id']}:")
                for v in r["violations"]:
                    print(f"    {v['rule']}: {v['detail']}")
            return 0

        if args.cover:
            try:
                cover_path = assemble_cover(
                    conn=conn,
                    run_id=args.run,
                    job_id=args.job,
                    palette=palette,
                    font=font,
                )
            except FileNotFoundError as e:
                print(f"error: {e}", file=sys.stderr)
                return 5
            print(f"cover: {cover_path}")
            return 0

        selection_payload: dict[str, Any] | None = None
        if args.selection is not None:
            try:
                selection_payload = json.loads(args.selection.read_text(encoding="utf-8"))
            except OSError as e:
                print(f"error: cannot read {args.selection}: {e}", file=sys.stderr)
                return 2
            except json.JSONDecodeError as e:
                print(f"error: invalid JSON in {args.selection}: {e}", file=sys.stderr)
                return 2
            errors = validate_selection_payload(selection_payload)
            if errors:
                print("schema error: selection.json: " + "; ".join(errors), file=sys.stderr)
                return 3
        try:
            result = assemble_one(
                conn=conn,
                run_id=args.run,
                job_id=args.job,
                palette=palette,
                font=font,
                selection=selection_payload,
            )
        except ValueError as e:
            # An id that is not a verified bullet, or a summary that fails the
            # voice gate. Loud, never silently dropped.
            print(f"selection rejected: {e}", file=sys.stderr)
            return 3
    finally:
        conn.close()

    print(f"cv: {result.cv_path}")
    print(f"selected components: {len(result.selected_component_ids)}")
    if result.gaps:
        print(f"semantic gaps ({len(result.gaps)}):")
        for g in result.gaps:
            print(f"  - {g}")
    missing_keywords = [kp for kp in result.keyword_presence if not kp["present"]]
    if missing_keywords:
        print(f"ATS keyword misses ({len(missing_keywords)}):")
        for kp in missing_keywords:
            print(f"  - {kp['requirement']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
