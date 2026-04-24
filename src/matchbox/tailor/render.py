"""Typst renderer — content dict → PDF.

Expects `typst` to be available on PATH.
Install: https://typst.app/

Convention:
  Template: shared/templates/{template_name}.typ
  Content:  written to a tmp JSON file, path passed via --input
  Output:   people/{name}/output/{run_id}-{tier}-{geo}.pdf
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _typst_binary() -> str:
    binary = shutil.which("typst")
    if binary is None:
        raise FileNotFoundError(
            "typst not found on PATH. Install from https://typst.app/ or `cargo install typst-cli`"
        )
    return binary


def render_pdf(
    template_name: str,
    content: dict[str, Any],
    output_path: Path,
    geo: str = "india",
) -> Path:
    """
    Compile a Typst template with content injected as JSON.

    Args:
        template_name: filename without extension under shared/templates/
        content:       content dict (from tailor/content.py or canonical)
        output_path:   destination PDF path
        geo:           "uk" | "india" | "relocate"

    Returns:
        output_path on success, raises subprocess.CalledProcessError on failure.
    """
    typst = _typst_binary()
    template = _repo_root() / "shared" / "templates" / f"{template_name}.typ"
    if not template.exists():
        raise FileNotFoundError(f"Typst template not found: {template}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(content, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    try:
        cmd = [
            typst, "compile",
            str(template),
            str(output_path),
            "--input", f"content_path={tmp_path}",
            "--input", f"geo={geo}",
        ]
        log.info("typst cmd: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            log.debug("typst stdout: %s", result.stdout)
    except subprocess.CalledProcessError as exc:
        log.error("typst failed:\n%s", exc.stderr)
        raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    log.info("rendered %s → %s", template_name, output_path)
    return output_path


def render_canonical(person_name: str, geo: str) -> Path:
    """
    Render (or return cached) the canonical pre-built PDF for this geo.

    Canonical PDFs are built once and reused at zero LLM cost.
    Path: people/{name}/output/canonical-{geo}.pdf
    """
    from matchbox.core.person import load_person
    from matchbox.core.schema import VALID_GEOS

    if geo not in VALID_GEOS:
        raise ValueError(f"Invalid geo {geo!r}. Valid: {sorted(VALID_GEOS)}")

    output_dir = _repo_root() / "people" / person_name / "output"
    cv_path = output_dir / f"canonical-{geo}.pdf"
    cover_path = output_dir / f"canonical-cover-{geo}.pdf"

    # Build content from raw profile (no LLM)
    person = load_person(person_name)
    canonical_content = _build_canonical_content(person, geo)

    render_pdf("cv-canonical", canonical_content, cv_path, geo=geo)
    render_pdf("cover-canonical", canonical_content, cover_path, geo=geo)

    return cv_path


def _build_canonical_content(person: Any, geo: str) -> dict[str, Any]:
    """Build a canonical content dict from profile.yaml — no LLM required."""
    p = person.profile
    c = p.candidate

    work_history = []
    for we in p.work_history:
        work_history.append({
            "company": we.company,
            "role": we.role,
            "dates": we.dates,
            "location": we.location,
            "bullets": [b.text for b in we.bullets],
        })

    projects = []
    for proj in p.projects:
        projects.append({
            "name": proj.name,
            "description": proj.description,
            "tags": proj.tags,
        })

    skills_by_category: dict[str, list[str]] = {}
    for s in p.skills:
        skills_by_category.setdefault(s.category or "Other", []).append(s.name)

    primary_role = next(iter(p.targets.primary_roles), "")

    return {
        "geo": geo,
        "candidate": {
            "full_name": c.full_name,
            "email": c.email,
            "phone": c.phone,
            "location": c.location,
            "linkedin": c.linkedin,
            "github": c.github,
            "website": c.website,
        },
        "headline": primary_role,
        "selected_work_history": work_history,
        "selected_projects": projects,
        "skills_by_category": skills_by_category,
        "cover_opening": "",
        "cover_body": [],
        "cover_closing": "",
        "_meta": {"tier": "canonical", "model": None, "cost_usd": 0.0},
    }
