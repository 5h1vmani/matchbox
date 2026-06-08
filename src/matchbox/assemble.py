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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from jsonschema import Draft202012Validator
from pypdf import PdfReader

from matchbox.core.db import PROJECT_ROOT, connect
from matchbox.core.migrations import migrate
from matchbox.matching.coverage import (
    BAND_COVERED,
    BAND_UNCOVERED,
    check_keyword_presence,
    coverage_band,
)
from matchbox.matching.embed import (
    DEFAULT_MODEL_VERSION,
    Embedder,
    FastEmbedEmbedder,
    cached_encode,
    cosine_matrix,
)
from matchbox.matching.select import (
    DEFAULT_WORD_BUDGET,
    SEMANTIC_COVERAGE_FLOOR,
    Component,
    Requirement,
    select_components,
)
from matchbox.polish import (
    BulletPolish,
    apply_polish,
    load_voice_rules,
    validate_polish_payload,
    validate_voice,
)

RUNS_DIR = PROJECT_ROOT / "runs"
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


def _load_unverified_bullets(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """(id, text) for every NOT-yet-verified bullet.

    Selection never touches these (the hard rule: no unverified content on the
    CV). They are consulted only for the coverage diagnostic, so a must-have the
    user genuinely has experience for -- but has not verified -- reads `partial`
    rather than a false `uncovered`."""
    rows = conn.execute(
        "SELECT id, text FROM bullet WHERE facts_verified = 0 ORDER BY id"
    ).fetchall()
    return [(r["id"], r["text"]) for r in rows]


def _semantic_coverage(
    *,
    requirements: list[Requirement],
    components: list[Component],
    selected_ids: list[int],
    similarity_matrix: np.ndarray,
    unverified: list[tuple[int, str]],
    unverified_sim: np.ndarray | None,
    floor: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-must-have coverage with a three-state band and the evidence bullet.

    For each must-have we compare its best similarity among the *selected*
    (verified, on-CV) bullets, among *all verified* library bullets, and among
    *unverified* bullets. The band (covered / partial / uncovered) and the
    argmax evidence bullet come straight from those similarities -- no
    fabrication. `gaps` keeps the original meaning (any must-have not fully
    covered) so existing readers and changes.md are unchanged."""
    comp_pos = {c.id: i for i, c in enumerate(components)}
    selected_pos = [comp_pos[cid] for cid in selected_ids if cid in comp_pos]
    have_sim = bool(similarity_matrix.size)

    out: list[dict[str, Any]] = []
    gaps: list[str] = []
    for j, r in enumerate(requirements):
        if r.type != "must-have":
            continue
        sel_pairs = (
            [(float(similarity_matrix[i, j]), components[i].id) for i in selected_pos]
            if have_sim
            else []
        )
        ver_pairs = (
            [(float(similarity_matrix[i, j]), c.id) for i, c in enumerate(components)]
            if have_sim
            else []
        )
        unv_pairs: list[tuple[float, int]] = []
        if unverified_sim is not None and unverified_sim.size:
            unv_pairs = [
                (float(unverified_sim[k, j]), unverified[k][0]) for k in range(len(unverified))
            ]
        sel_best, sel_id = max(sel_pairs, default=(0.0, None))
        ver_best, ver_id = max(ver_pairs, default=(0.0, None))
        unv_best, unv_id = max(unv_pairs, default=(0.0, None))

        band = coverage_band(
            selected_best=sel_best, library_best=max(ver_best, unv_best), floor=floor
        )
        if band == BAND_COVERED:
            evidence_id, evidence_verified = sel_id, True
        elif band == BAND_UNCOVERED:
            evidence_id, evidence_verified = None, None
        elif ver_best >= unv_best:
            evidence_id, evidence_verified = ver_id, True
        else:
            evidence_id, evidence_verified = unv_id, False

        if band != BAND_COVERED:
            gaps.append(r.text)
        out.append(
            {
                "text": r.text,
                "covered": band == BAND_COVERED,
                "band": band,
                "evidence_bullet_id": evidence_id,
                "evidence_verified": evidence_verified,
            }
        )
    return out, gaps


_SCHEMAS_DIR = PROJECT_ROOT / "schemas"


def _selection_validator() -> Draft202012Validator:
    schema = json.loads((_SCHEMAS_DIR / "selection.v1.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_selection_payload(payload: dict[str, Any]) -> list[str]:
    """Schema-validate a brain selection payload. Returns human-readable errors
    (empty when valid)."""
    return [e.message for e in _selection_validator().iter_errors(payload)]


def _apply_selection(
    selection: dict[str, Any], components: list[Component]
) -> tuple[list[int], dict[int, float], str]:
    """Validate the brain's selection against the verified library and the voice
    gate; return (ordered_ids, rank_relevance, summary).

    The no-fabrication guarantee is enforced HERE, not by selection being an
    algorithm: every id must be a verified library bullet, or we reject loudly.
    The brain emits ids only (never bullet text), so the selected text is
    unmodified by construction. The summary is voice-gated like a cover letter;
    its truthfulness is the brain's responsibility.
    """
    valid = {c.id for c in components}
    ids = [int(i) for i in selection["selected_bullet_ids"]]
    unknown = [i for i in ids if i not in valid]
    if unknown:
        raise ValueError(
            "selection references ids that are not verified library bullets: "
            + ", ".join(map(str, unknown))
        )
    seen: set[int] = set()
    ordered: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)

    summary = str(selection["summary"]).strip()
    violations = validate_voice(summary, load_voice_rules(), scope="summary")
    if violations:
        raise ValueError(
            "summary failed the voice gate: "
            + "; ".join(f"{v.rule}: {v.detail}" for v in violations)
        )

    # Rank-relevance: earlier in the brain's order = more important (drives the
    # changes.md display). One-page safety belt: keep the brain's order, drop the
    # lowest-priority (trailing) bullets once the body exceeds the word budget.
    relevance = {cid: float(len(ordered) - rank) for rank, cid in enumerate(ordered)}
    text_by_id = {c.id: c.text for c in components}
    kept: list[int] = []
    used = 0
    for cid in ordered:
        words = len(text_by_id[cid].split())
        if kept and used + words > DEFAULT_WORD_BUDGET:
            break
        kept.append(cid)
        used += words
    return kept, relevance, summary


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


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}

# A role that names a degree -> the row is education, not work. Disambiguates the
# common case where one institution holds both a degree and a job (e.g. an MSc and
# a Research Assistant role at the same university): the ROLE decides, not the
# employer. Deliberately strict so job titles like "Senior Associate" do not match.
_DEGREE_RE = re.compile(
    r"(?i)\b("
    r"bachelor|master|doctor(?:ate)?|ph\.?d|mba|"
    r"b\.?(?:sc|com|tech|a|e|ed|arch)|m\.?(?:sc|com|tech|a|e|ed|arch|phil)|"
    r"ll\.?[bm]|diploma|associate of (?:arts|science)"
    r")\b"
)


def _is_degree_role(role: str | None) -> bool:
    return bool(_DEGREE_RE.search(role or ""))


def _exp_date_key(date_str: str | None) -> tuple[int, int]:
    """Sortable (year, month) from a free-text experience date.

    "present"/"" -> (9999, 13) so an ongoing role sorts newest. "Aug 2025" ->
    (2025, 8); a bare "2014" -> (2014, 0). Unparsable text sinks to (0, 0) rather
    than corrupting the order. Tolerant of month name + year in either position.
    """
    s = (date_str or "").strip().lower()
    if not s or s == "present":
        return (9999, 13)
    month = 0
    year = 0
    for tok in s.replace(",", " ").split():
        if tok[:3] in _MONTHS:
            month = _MONTHS[tok[:3]]
        elif tok.isdigit() and len(tok) == 4:
            year = int(tok)
    return (year, month)


def _experiences_in_order(
    components: list[Component], raw_bullets: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group selected components into experiences, ordered reverse-chronologically
    and grouped by employer.

    Reverse-chronological (newest first, "present" on top) is the CV standard:
    ATS parsers map the first dated block as the current role, and recruiters scan
    top-down expecting recency. Grouping by employer keeps a company's roles
    adjacent and newest-first, so a promotion reads as progression instead of
    scattering across the page. Bullet order within a role is left as the brain
    chose it (impact-first).
    """
    by_exp: dict[int, dict[str, Any]] = {}
    for c in components:
        b = raw_bullets[c.id]
        ex_id = c.experience_id
        if ex_id not in by_exp:
            by_exp[ex_id] = {
                "_exp_id": ex_id,
                "company": b["company"],
                "role": b["role"],
                "start_date": b["start_date"] or "",
                "end_date": b["end_date"] or "present",
                "location": b["location"],
                "bullets": [],
            }
        cast(list[str], by_exp[ex_id]["bullets"]).append(b["text"])

    rows = list(by_exp.values())
    role_key = {
        x["_exp_id"]: (_exp_date_key(x["end_date"]), _exp_date_key(x["start_date"])) for x in rows
    }
    # Each company sorts by its most-recent role, so every role at one employer
    # stays together (newest first) rather than scattering between other companies.
    company_key: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    for x in rows:
        company_key[x["company"]] = max(
            company_key.get(x["company"], ((0, 0), (0, 0))), role_key[x["_exp_id"]]
        )
    ordered = sorted(
        rows,
        key=lambda x: (company_key[x["company"]], role_key[x["_exp_id"]]),
        reverse=True,
    )
    for ex in ordered:
        ex.pop("_exp_id", None)
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

    # Education: degrees live in the `experience` table, so route the degree-roles
    # into their own section (newest first). Shown on every CV regardless of
    # bullet selection -- credentials are not bullets. Work experiences drop any
    # degree-role for the same reason, so a degree never renders as a job.
    work = [e for e in experiences if not _is_degree_role(e.get("role"))]
    degree_rows = [
        r
        for r in conn.execute(
            "SELECT company, role, start_date, end_date FROM experience"
        ).fetchall()
        if _is_degree_role(r["role"])
    ]
    degree_rows.sort(
        key=lambda r: (_exp_date_key(r["end_date"]), _exp_date_key(r["start_date"])),
        reverse=True,
    )
    education = [
        {
            "degree": r["role"],
            "school": r["company"],
            "dates": " to ".join(d for d in (r["start_date"], r["end_date"]) if d)
            or (r["end_date"] or ""),
        }
        for r in degree_rows
    ]

    return {
        "schema_version": 1,
        "profile": {
            "name": str(profile.get("full_name", "Your Name")),
            "headline": str(profile.get("headline") or ""),
            "contact": contact,
        },
        "summary": summary_text,
        "experiences": work,
        "projects": [],
        "skills": skills,
        "education": education,
    }


def _pick_summary(conn: sqlite3.Connection) -> str:
    """The brain may eventually pick a tagged summary_variant; for v1
    we use the most recently added one, if any."""
    row = conn.execute("SELECT text FROM summary_variant ORDER BY id DESC LIMIT 1").fetchone()
    return str(row[0]) if row else ""


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
    selection: dict[str, Any] | None = None,
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

    # Build the CV JSON, bullets in the chosen order (the brain's order when
    # supplied, library order otherwise).
    comp_by_id = {c.id: c for c in components}
    chosen = [comp_by_id[i] for i in selected_ids]
    experiences = _experiences_in_order(chosen, raw_bullets)
    cv_json = _build_cv_json(
        profile=profile,
        experiences=experiences,
        summary_text=summary_text,
        conn=conn,
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
    _render_pdf(cv_json_path, cv_pdf_path, palette, font)

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

    job = _load_job(conn, job_id)
    changes_path = _write_changes_md(
        out_dir=out_dir,
        job_company=str(job["company"]),
        job_title=str(job["title"]),
        selected_ids=selected_ids,
        components=components,
        requirements=requirements,
        similarity_matrix=sim,
        relevance=relevance,
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
        selected_component_ids=selected_ids,
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
