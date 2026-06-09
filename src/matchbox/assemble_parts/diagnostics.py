"""Coverage diagnostic: per-must-have three-state band (covered / partial /
uncovered) with the evidence bullet, plus the requirement embedding-cache id.
Extracted from assemble.py. (Distinct from matching.coverage, which holds the
band thresholds and keyword-presence check this builds on.)"""

from __future__ import annotations

from typing import Any

import numpy as np

from matchbox.matching.coverage import BAND_COVERED, BAND_UNCOVERED, coverage_band
from matchbox.matching.select import Component, Requirement


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


def _requirement_synth_id(job_id: int, idx: int) -> int:
    """Pack (job_id, idx) into a single int for the embedding cache. Small
    multiplier keeps ids unique per job up to 10k requirements per job."""
    return job_id * 10_000 + idx
