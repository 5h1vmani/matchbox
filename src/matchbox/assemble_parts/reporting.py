"""changes.md generation for the assemble and polish paths: the human-readable
audit of which verified bullets were selected, which were skipped, uncovered
must-haves, ATS keyword misses, and polish results. Extracted from assemble.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matchbox.matching.select import Component, Requirement
from matchbox.polish import BulletPolish


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
