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
import hashlib
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
from matchbox.polish import (
    BulletPolish,
    apply_polish,
    validate_polish_payload,
)

RUNS_DIR = PROJECT_ROOT / "runs"
TEMPLATE_DIR = PROJECT_ROOT / "src" / "matchbox" / "templates" / "typst"
CV_TEMPLATE = TEMPLATE_DIR / "cv.typ"
COVER_TEMPLATE = TEMPLATE_DIR / "cover.typ"
# Fonts are bundled in-repo and passed to Typst via --font-path, so renders do
# not depend on system-installed fonts. The old template named fonts that were
# never installed (Source Serif Pro, Inter), so every render silently fell back
# to a Typst default. Bundling makes typography deterministic and portable.
FONTS_DIR = PROJECT_ROOT / "shared" / "fonts"
DEFAULT_K = 12  # max bullets across all roles


@dataclass(slots=True)
class AssembleResult:
    cv_path: Path
    cv_json_path: Path
    coverage_report_path: Path
    changes_md_path: Path
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


def _write_changes_md(
    *,
    out_dir: Path,
    job_company: str,
    job_title: str,
    selected_ids: list[int],
    relevance: dict[int, float],
    raw_bullets: dict[int, dict[str, Any]],
    semantic_gaps: list[str],
    keyword_presence: list[Any],
    components: list[Component] | None = None,
    requirements: list[Requirement] | None = None,
    similarity_matrix: Any = None,
    candidate_count: int = 2,
) -> Path:
    """Write a human-readable summary of what changed vs. the master library.

    The "master" baseline is every verified bullet in the library, grouped
    by experience. The tailored CV shows a subset. This document spells
    out exactly which bullets made it and which were dropped, with
    relevance scores, so the user can sanity-check the matcher's choices.
    """
    selected_set = set(selected_ids)
    grouped: dict[int, dict[str, Any]] = {}
    for bullet_id, row in raw_bullets.items():
        ex_id = row["experience_id"]
        if ex_id not in grouped:
            grouped[ex_id] = {
                "_sort": row["sort_order"],
                "company": row["company"],
                "role": row["role"],
                "start_date": row["start_date"] or "",
                "end_date": row["end_date"] or "present",
                "selected": [],
                "skipped": [],
            }
        bucket = "selected" if bullet_id in selected_set else "skipped"
        grouped[ex_id][bucket].append(
            {
                "id": bullet_id,
                "text": row["text"],
                "relevance": relevance.get(bullet_id, 0.0),
            }
        )
    ordered = sorted(grouped.values(), key=lambda g: g["_sort"])

    lines: list[str] = []
    lines.append(f"# Changes for {job_company} — {job_title}")
    lines.append("")
    total_selected = len(selected_set)
    total_library = len(raw_bullets)
    lines.append(
        f"Selected **{total_selected}** of **{total_library}** verified bullets "
        f"across **{len(grouped)}** role{'' if len(grouped) == 1 else 's'}."
    )
    lines.append("")

    for ex in ordered:
        lines.append(f"## {ex['company']} — {ex['role']}")
        lines.append(f"_{ex['start_date']} → {ex['end_date']}_")
        lines.append("")
        if ex["selected"]:
            lines.append("**Selected:**")
            for b in sorted(ex["selected"], key=lambda x: -x["relevance"]):
                lines.append(f"- ({b['relevance']:.2f}) {b['text']}")
            lines.append("")
        if ex["skipped"]:
            lines.append("**Skipped:**")
            for b in sorted(ex["skipped"], key=lambda x: -x["relevance"]):
                lines.append(f"- ({b['relevance']:.2f}) {b['text']}")
            lines.append("")

    if semantic_gaps:
        lines.append("## Uncovered must-haves")
        lines.append("")
        lines.append(
            "These JD requirements have no verified bullet matching above the "
            "semantic floor. Consider adding a bullet that describes the work, "
            "or marking the requirement as something you cannot honestly claim."
        )
        lines.append("")
        for g in semantic_gaps:
            lines.append(f"- {g}")
        lines.append("")

    missing_keywords = [kp for kp in keyword_presence if not kp.present]
    if missing_keywords:
        lines.append("## ATS keyword misses")
        lines.append("")
        lines.append(
            "A literal ATS would not find these terms in the rendered CV, even "
            "though the matcher considers the requirement semantically covered. "
            "The polish pass can rephrase a selected bullet to carry the term, "
            "if doing so remains truthful."
        )
        lines.append("")
        # Build a sim lookup by requirement text → column index.
        req_idx_by_text: dict[str, int] = {}
        if requirements is not None:
            for ridx, r in enumerate(requirements):
                req_idx_by_text[r.text] = ridx
        comp_idx_by_id: dict[int, int] = {}
        if components is not None:
            for cidx, c in enumerate(components):
                comp_idx_by_id[c.id] = cidx

        for kp in missing_keywords:
            lines.append(f"- **{kp.requirement_text}**")
            req_idx = req_idx_by_text.get(kp.requirement_text)
            if (
                req_idx is not None
                and similarity_matrix is not None
                and components is not None
                and similarity_matrix.size
            ):
                # Score each selected bullet against this requirement;
                # surface the top N as polish candidates.
                candidates: list[tuple[int, float]] = []
                for cid in selected_ids:
                    comp_idx = comp_idx_by_id.get(cid)
                    if comp_idx is None:
                        continue
                    sim = float(similarity_matrix[comp_idx, req_idx])
                    candidates.append((cid, sim))
                candidates.sort(key=lambda x: -x[1])
                top = [c for c in candidates if c[0] in raw_bullets][:candidate_count]
                if top:
                    lines.append("  Polish candidates (highest semantic similarity):")
                    for cid, sim in top:
                        lines.append(f"    - ({sim:.2f}) {raw_bullets[cid]['text']}")
        lines.append("")

    out_path = out_dir / "changes.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


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
    """Render the CV from cv.json to PDF.

    Uses the in-repo HTML/CSS template plus weasyprint (pure Python, no
    browser): the v0.1 layout, and pdftotext reads it in correct order. The
    populated HTML is written beside cv.json so the artifact dir stays
    self-contained and re-renderable.
    """
    from matchbox.render_html import render_cv_pdf

    render_cv_pdf(cv_json_path, out_path, palette=palette, font=font)


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
    coverage_floor: float = SEMANTIC_COVERAGE_FLOOR,
) -> AssembleResult:
    """Selection + render path for a single job. Returns the artifact paths
    and the gaps / keyword-presence reports.

    `coverage_floor` defaults to the production value (0.5) tuned for
    bge-small-en-v1.5. Tests that use a weak FakeEmbedder pass a lower
    value explicitly.
    """
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
        coverage_floor=coverage_floor,
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
    # Fingerprint the selected bullets so re_render_cv can warn when the
    # DB has drifted (the user edited a bullet after this render).
    cv_json["_selected_bullets"] = [{"id": c.id, "text_hash": _bullet_hash(c.text)} for c in chosen]

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
            "floor": coverage_floor,
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

    job = _load_job(conn, job_id)
    changes_path = _write_changes_md(
        out_dir=out_dir,
        job_company=str(job["company"]),
        job_title=str(job["title"]),
        selected_ids=result.selected_ids,
        components=components,
        requirements=requirements,
        similarity_matrix=result.similarity_matrix,
        relevance=result.relevance_by_component,
        raw_bullets=raw_bullets,
        semantic_gaps=semantic_gaps,
        keyword_presence=keyword_presence,
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
        selected_component_ids=result.selected_ids,
    )


def _requirement_synth_id(job_id: int, idx: int) -> int:
    """Pack (job_id, idx) into a single int for the embedding cache. Small
    multiplier keeps ids unique per job up to 10k requirements per job."""
    return job_id * 10_000 + idx


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


def _append_polish_section_to_changes_md(
    *,
    out_dir: Path,
    applied: list[BulletPolish],
    rejected: list[BulletPolish],
) -> None:
    """Append a 'Polished' section to changes.md so the user can read
    exactly how the wording changed and why anything was rejected."""
    changes_path = out_dir / "changes.md"
    lines: list[str] = []
    if changes_path.exists():
        lines.append("")  # spacer if appending
    lines.append("## Polished")
    lines.append("")
    if applied:
        for bp in applied:
            covers = f" (covers: {', '.join(bp.covers)})" if bp.covers else ""
            lines.append(f"- **bullet {bp.bullet_id}**{covers}")
            if bp.original_text:
                lines.append(f"  - was: {bp.original_text}")
            lines.append(f"  - now: {bp.new_text}")
    else:
        lines.append("_No bullets applied._")
    if rejected:
        lines.append("")
        lines.append("### Rejected")
        lines.append("")
        for bp in rejected:
            why = "; ".join(f"{v.rule}: {v.detail}" for v in bp.violations)
            lines.append(f"- bullet {bp.bullet_id} — {why}")
            lines.append(f"  - proposed: {bp.new_text}")
    lines.append("")

    if changes_path.exists():
        existing = changes_path.read_text(encoding="utf-8")
        changes_path.write_text(existing + "\n".join(lines), encoding="utf-8")
    else:
        changes_path.write_text("\n".join(lines), encoding="utf-8")


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
        "--font-path",
        str(FONTS_DIR),
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
    parser.add_argument(
        "--polish",
        type=Path,
        default=None,
        metavar="POLISH_JSON",
        help="apply a polish payload (per schemas/polish.v1.json) to an already-rendered run",
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
