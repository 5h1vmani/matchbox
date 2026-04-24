"""Tailor dispatch — routes a job to bespoke, template, or canonical path.

Entry point: tailor_job(job, person) -> Application

Path summary:
  bespoke:   content.generate_content → gates → render.render_pdf × 2
  template:  content.generate_content (lighter prompt) → gates → render.render_pdf × 2
  canonical: copy pre-rendered PDF (zero LLM cost)
  skip:      return None immediately
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from matchbox.core import db
from matchbox.core.schema import Application, Job, Person
from matchbox.scoring.tier_router import infer_geo
from matchbox.tailor.content import generate_content
from matchbox.tailor.gates import GateViolation, run_all_gates
from matchbox.tailor.render import render_canonical, render_pdf

log = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _output_dir(person_name: str, job_id: int | None) -> Path:
    tag = str(job_id) if job_id else "draft"
    return _repo_root() / "people" / person_name / "output" / tag


def tailor_job(
    job: Job,
    person: Person,
    *,
    model: str = "claude-sonnet-4-6",
    gate_mode: str = "warn",  # "warn" | "raise" | "skip"
) -> Application | None:
    """
    Generate tailored CV + cover for a job. Returns Application or None if skip.

    gate_mode controls what happens when quality gates fail:
      "warn"  — log violations, continue
      "raise" — raise GateFailureError
      "skip"  — log violations, return None
    """
    tier = job.tier or "canonical"
    geo = infer_geo(job.country)

    if tier == "skip":
        log.info("skip tier — no output generated for job_id=%s", job.id)
        return None

    if tier == "canonical":
        return _canonical_path(job, person, geo)

    return _llm_path(job, person, tier=tier, geo=geo, model=model, gate_mode=gate_mode)


def _canonical_path(job: Job, person: Person, geo: str) -> Application:
    """Copy pre-rendered canonical PDF into the job output directory."""
    canonical_cv = _repo_root() / "people" / person.name / "output" / f"canonical-{geo}.pdf"
    canonical_cover = (
        _repo_root() / "people" / person.name / "output" / f"canonical-cover-{geo}.pdf"
    )

    # Rebuild canonical if not present
    if not canonical_cv.exists():
        log.info("canonical PDF missing for geo=%s — rebuilding", geo)
        render_canonical(person.name, geo)

    out_dir = _output_dir(person.name, job.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    cv_dest = out_dir / f"cv-canonical-{geo}.pdf"
    cover_dest = out_dir / f"cover-canonical-{geo}.pdf"

    shutil.copy2(canonical_cv, cv_dest)
    if canonical_cover.exists():
        shutil.copy2(canonical_cover, cover_dest)

    app = Application(
        job_id=job.id or 0,
        profile_name=person.name,
        tier="canonical",
        geo=geo,
        cv_path=str(cv_dest),
        cover_path=str(cover_dest) if canonical_cover.exists() else None,
        cost_usd=0.0,
        content={},
    )

    if job.id:
        db.mark_tailored(
            person.name,
            job.id,
            cv_path=str(cv_dest),
            cover_path=str(cover_dest) if canonical_cover.exists() else None,
            tier="canonical",
            cost_usd=0.0,
        )

    log.info("canonical path done job_id=%s geo=%s", job.id, geo)
    return app


def _llm_path(
    job: Job,
    person: Person,
    *,
    tier: str,
    geo: str,
    model: str,
    gate_mode: str,
) -> Application | None:
    """Run LLM content gen → gates → render for bespoke or template."""
    content = generate_content(job, person, model=model)
    cost = content.get("_meta", {}).get("cost_usd", 0.0)

    # Extract bullets and cover for gate check
    all_bullets: list[str] = [
        b for entry in content.get("selected_work_history", []) for b in entry.get("bullets", [])
    ]
    cover_text = " ".join(
        [
            content.get("cover_opening", ""),
            *content.get("cover_body", []),
            content.get("cover_closing", ""),
        ]
    )

    violations: list[GateViolation] = run_all_gates(all_bullets, cover_text, person.voice)
    if violations:
        violation_str = "\n".join(str(v) for v in violations)
        if gate_mode == "raise":
            from matchbox.core.exceptions import GateFailureError

            raise GateFailureError(f"{len(violations)} gate violation(s):\n{violation_str}")
        elif gate_mode == "skip":
            log.warning(
                "gate_mode=skip, abandoning tailor for job_id=%s\n%s", job.id, violation_str
            )
            return None
        else:
            log.warning("gate violations (continuing):\n%s", violation_str)

    out_dir = _output_dir(person.name, job.id)
    cv_path = render_pdf("cv-canonical", content, out_dir / f"cv-{tier}-{geo}.pdf", geo=geo)
    cover_path = render_pdf(
        "cover-canonical", content, out_dir / f"cover-{tier}-{geo}.pdf", geo=geo
    )

    app = Application(
        job_id=job.id or 0,
        profile_name=person.name,
        tier=tier,
        geo=geo,
        cv_path=str(cv_path),
        cover_path=str(cover_path),
        cost_usd=cost,
        content=content,
    )

    if job.id:
        db.mark_tailored(
            person.name,
            job.id,
            cv_path=str(cv_path),
            cover_path=str(cover_path),
            tier=tier,
            cost_usd=cost,
        )

    log.info("llm path done job_id=%s tier=%s geo=%s cost=%.4f", job.id, tier, geo, cost)
    return app


def rebuild_canonicals(person_name: str) -> dict[str, Path]:
    """Regenerate all 3 geo variants of the canonical PDF. Called via CLI."""
    from matchbox.core.schema import VALID_GEOS

    results: dict[str, Path] = {}
    for geo in sorted(VALID_GEOS):
        path = render_canonical(person_name, geo)
        results[geo] = path
        log.info("rebuilt canonical geo=%s → %s", geo, path)
    return results
