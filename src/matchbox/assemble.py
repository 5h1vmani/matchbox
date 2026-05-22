"""assemble — deterministic selection + Typst render for one job.

The brain invokes this once per job in a run:

    python -m matchbox.assemble --run <run_id> --job <job_id>
    python -m matchbox.assemble --run <run_id> --job <job_id> --cover

The first form builds the CV (selects components, renders cv.pdf, runs
the coverage checks). The second form renders a cover letter from text
the brain has already written into runs/<run>/output/<job>/cover.txt.

This module is the single place selection lives — the brain does not
pick component ids. That keeps the path reproducible and unit-testable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pypdf import PdfReader

from matchbox.core.db import PROJECT_ROOT, connect
from matchbox.core.migrations import migrate
from matchbox.matching.coverage import check_keyword_presence
from matchbox.matching.embed import (
    DEFAULT_MODEL_VERSION,
    Embedder,
    FastEmbedEmbedder,
    cached_encode,
)
from matchbox.matching.select import (
    SEMANTIC_COVERAGE_FLOOR,
    Component,
    Requirement,
    select_components,
)

RUNS_DIR = PROJECT_ROOT / "runs"
TEMPLATE_DIR = PROJECT_ROOT / "src" / "matchbox" / "templates" / "typst"
CV_TEMPLATE = TEMPLATE_DIR / "cv.typ"
COVER_TEMPLATE = TEMPLATE_DIR / "cover.typ"
DEFAULT_K = 12  # max bullets across all roles


@dataclass(slots=True)
class AssembleResult:
    cv_path: Path
    cv_json_path: Path
    coverage_report_path: Path
    gaps: list[str]
    keyword_presence: list[dict[str, object]]
    selected_component_ids: list[int]


def _load_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise LookupError(f"job {job_id} not found in DB")
    return dict(row)


def _load_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profile LIMIT 1").fetchone()
    return dict(row) if row is not None else {}


def _load_components(
    conn: sqlite3.Connection,
) -> tuple[list[Component], dict[int, dict[str, Any]]]:
    """Verified bullets only. Returns (Components, raw_bullet_by_id)."""
    rows = conn.execute(
        """
        SELECT b.id, b.experience_id, b.text, b.has_metric,
               e.company, e.role, e.start_date, e.end_date, e.location, e.sort_order
          FROM bullet b
          JOIN experience e ON e.id = b.experience_id
         WHERE b.facts_verified = 1
         ORDER BY e.sort_order, e.id, b.id
        """
    ).fetchall()
    comps = [
        Component(
            id=r["id"],
            text=r["text"],
            experience_id=r["experience_id"],
            has_metric=bool(r["has_metric"]),
            end_date=r["end_date"],
        )
        for r in rows
    ]
    raw = {r["id"]: dict(r) for r in rows}
    return comps, raw


def _load_requirements(conn: sqlite3.Connection, job_id: int) -> list[Requirement]:
    row = conn.execute("SELECT requirements_json FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None or not row["requirements_json"]:
        return []
    payload = json.loads(row["requirements_json"])
    return [
        Requirement(
            text=r["text"],
            type=r["type"],
            keywords=r.get("keywords", []),
            variants=r.get("variants", []),
        )
        for r in payload.get("requirements", [])
    ]


def _experiences_in_order(
    components: list[Component], raw_bullets: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group selected components back into experiences for the CV JSON."""
    by_exp: dict[int, dict[str, Any]] = {}
    for c in components:
        b = raw_bullets[c.id]
        ex_id = c.experience_id
        if ex_id not in by_exp:
            by_exp[ex_id] = {
                "_sort_order": b["sort_order"],
                "_exp_id": ex_id,
                "company": b["company"],
                "role": b["role"],
                "start_date": b["start_date"] or "",
                "end_date": b["end_date"] or "present",
                "location": b["location"],
                "bullets": [],
            }
        cast(list[str], by_exp[ex_id]["bullets"]).append(b["text"])
    ordered = sorted(by_exp.values(), key=lambda x: (x["_sort_order"], x["_exp_id"]))
    for ex in ordered:
        ex.pop("_sort_order")
        ex.pop("_exp_id")
    return ordered


def _build_cv_json(
    *,
    profile: dict[str, Any],
    experiences: list[dict[str, Any]],
    summary_text: str,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    skills_rows = conn.execute(
        "SELECT category, name FROM skill ORDER BY category, name"
    ).fetchall()
    skill_by_cat: dict[str, list[str]] = {}
    for r in skills_rows:
        cat = r["category"] or "Other"
        skill_by_cat.setdefault(cat, []).append(r["name"])
    skills = [{"category": cat, "items": items} for cat, items in skill_by_cat.items()]

    contact: list[str] = []
    if profile.get("email"):
        contact.append(str(profile["email"]))
    if profile.get("phone"):
        contact.append(str(profile["phone"]))
    if profile.get("location"):
        contact.append(str(profile["location"]))
    links = json.loads(str(profile.get("links_json") or "[]"))
    contact.extend(links)

    return {
        "schema_version": 1,
        "profile": {
            "name": str(profile.get("full_name", "Your Name")),
            "headline": str(profile.get("headline") or ""),
            "contact": contact,
        },
        "summary": summary_text,
        "experiences": experiences,
        "projects": [],
        "skills": skills,
        "education": [],
    }


def _pick_summary(conn: sqlite3.Connection) -> str:
    """The brain may eventually pick a tagged summary_variant; for v1
    we use the most recently added one, if any."""
    row = conn.execute("SELECT text FROM summary_variant ORDER BY id DESC LIMIT 1").fetchone()
    return str(row[0]) if row else ""


def _ensure_typst() -> str:
    typst = shutil.which("typst")
    if not typst:
        raise FileNotFoundError(
            "typst not found on PATH. Install: https://github.com/typst/typst#installation"
        )
    return typst


def _render_pdf(cv_json_path: Path, out_path: Path, palette: str, font: str) -> None:
    """Render the Typst CV.

    Typst restricts file reads to `--root`. We copy the template alongside
    cv.json into the output dir and set --root to that dir, so both files
    are reachable and the render is fully self-contained (re-runnable
    from the artifact dir alone).
    """
    typst = _ensure_typst()
    root_dir = cv_json_path.parent
    local_template = root_dir / "cv.typ"
    shutil.copy2(CV_TEMPLATE, local_template)

    cmd = [
        typst,
        "compile",
        str(local_template),
        str(out_path),
        "--root",
        str(root_dir),
        "--input",
        f"data={cv_json_path.name}",
        "--input",
        f"palette={palette}",
        "--input",
        f"font={font}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"typst compile failed (rc={proc.returncode}):\n{proc.stderr or proc.stdout}"
        )


def _extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def assemble_one(
    *,
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
    embedder: Embedder | None = None,
) -> AssembleResult:
    """Selection + render path for a single job. Returns the artifact paths
    and the gaps / keyword-presence reports."""
    _load_job(conn, job_id)  # ensure the job exists; raises LookupError
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

    result = select_components(
        components=components,
        component_embeddings=component_vecs,
        requirements=requirements,
        requirement_embeddings=requirement_vecs,
        k=DEFAULT_K,
        per_role_cap=4,
    )

    # Build the CV JSON with only the selected bullets.
    selected_set = set(result.selected_ids)
    chosen = [c for c in components if c.id in selected_set]
    experiences = _experiences_in_order(chosen, raw_bullets)
    cv_json = _build_cv_json(
        profile=profile,
        experiences=experiences,
        summary_text=_pick_summary(conn),
        conn=conn,
    )

    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_json_path = out_dir / "cv.json"
    cv_json_path.write_text(json.dumps(cv_json, indent=2), encoding="utf-8")

    cv_pdf_path = out_dir / "cv.pdf"
    _render_pdf(cv_json_path, cv_pdf_path, palette, font)

    # Coverage reports.
    pdf_text = _extract_pdf_text(cv_pdf_path)
    keyword_presence = check_keyword_presence(pdf_text, requirements)
    semantic_gaps: list[str] = [
        r.text
        for r, ok in zip(
            [r for r in requirements if r.type == "must-have"], result.covered, strict=True
        )
        if not ok
    ]

    coverage = {
        "semantic": {
            "floor": SEMANTIC_COVERAGE_FLOOR,
            "must_haves": [
                {"text": r.text, "covered": ok}
                for r, ok in zip(
                    [r for r in requirements if r.type == "must-have"],
                    result.covered,
                    strict=True,
                )
            ],
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

    return AssembleResult(
        cv_path=cv_pdf_path,
        cv_json_path=cv_json_path,
        coverage_report_path=coverage_path,
        gaps=semantic_gaps,
        keyword_presence=[
            {"requirement": kp.requirement_text, "present": kp.present, "matched": kp.matched_term}
            for kp in keyword_presence
        ],
        selected_component_ids=result.selected_ids,
    )


def _requirement_synth_id(job_id: int, idx: int) -> int:
    """Pack (job_id, idx) into a single int for the embedding cache. Small
    multiplier keeps ids unique per job up to 10k requirements per job."""
    return job_id * 10_000 + idx


# ─── re-render path (palette/font swap, no selection) ────────────────


def re_render_cv(
    *,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
) -> Path:
    """Re-render a finished CV with a new palette/font. Requires cv.json
    to exist in the output dir. No DB / no brain involvement."""
    out_dir = RUNS_DIR / run_id / "output" / str(job_id)
    cv_json_path = out_dir / "cv.json"
    if not cv_json_path.exists():
        raise FileNotFoundError(f"cv.json not found for run {run_id}, job {job_id}. Tailor first.")
    cv_pdf_path = out_dir / "cv.pdf"
    _render_pdf(cv_json_path, cv_pdf_path, palette, font)
    return cv_pdf_path


# ─── cover letter render ──────────────────────────────────────────────


def _render_cover_pdf(
    cover_txt_path: Path,
    cover_meta_path: Path,
    out_path: Path,
    palette: str,
    font: str,
) -> None:
    typst = _ensure_typst()
    root_dir = cover_txt_path.parent
    local_template = root_dir / "cover.typ"
    shutil.copy2(COVER_TEMPLATE, local_template)
    cmd = [
        typst,
        "compile",
        str(local_template),
        str(out_path),
        "--root",
        str(root_dir),
        "--input",
        f"data={cover_txt_path.name}",
        "--input",
        f"meta={cover_meta_path.name}",
        "--input",
        f"palette={palette}",
        "--input",
        f"font={font}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"typst compile failed (rc={proc.returncode}):\n{proc.stderr or proc.stdout}"
        )


def assemble_cover(
    *,
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
    palette: str,
    font: str,
) -> Path:
    """Render cover.txt → cover.pdf. The brain writes cover.txt; this
    builds cover_meta.json from the profile + job, then calls Typst."""
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

    meta = {
        "candidate_name": str(profile.get("full_name", "Your Name")),
        "contact": contact,
        "date": datetime.now(UTC).strftime("%B %d, %Y"),
        "recipient": ["Hiring Team", str(job["company"])],
        "salutation": "Dear Hiring Team,",
        "closing": "Sincerely,",
    }
    cover_meta = out_dir / "cover_meta.json"
    cover_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    cover_pdf = out_dir / "cover.pdf"
    _render_cover_pdf(cover_txt, cover_meta, cover_pdf, palette, font)
    return cover_pdf


def _palette_and_font_for(
    conn: sqlite3.Connection,
    run_id: str,
    job_id: int,
) -> tuple[str, str]:
    row = conn.execute(
        "SELECT palette, font FROM run_job WHERE run_id = ? AND job_id = ?",
        (run_id, job_id),
    ).fetchone()
    if row is None:
        return "slate", "source-serif"
    return row["palette"], row["font"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run id (YYYY-MM-DD-NNN)")
    parser.add_argument("--job", required=True, type=int, help="job id")
    parser.add_argument(
        "--cover",
        action="store_true",
        help="render the cover letter (reads cover.txt the brain wrote)",
    )
    parser.add_argument("--db", type=Path, default=None, help="override DB path")
    args = parser.parse_args(argv)

    conn = connect(args.db) if args.db else connect()
    try:
        migrate(conn)
        palette, font = _palette_and_font_for(conn, args.run, args.job)

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

        result = assemble_one(
            conn=conn,
            run_id=args.run,
            job_id=args.job,
            palette=palette,
            font=font,
        )
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
