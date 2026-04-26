"""Profile editor adapter — read & atomically rewrite scoring weights,
plus the pure-function preview that shows what new weights would do.

The structural parts of profile.yaml (work history, voice rules, archetypes)
stay hand-edited. Only the 6 scoring weights are mutable from the UI.

Round-trip uses ruamel.yaml so comments and key order are preserved.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from matchbox.core import db
from matchbox.core.schema import Job, ScoringWeights
from matchbox.scoring.rubric import weighted_total
from matchbox.web.config import Settings


class ProfileYamlError(ValueError):
    """Raised when profile.yaml is missing or malformed."""


log = logging.getLogger(__name__)

WEIGHT_FIELDS: tuple[str, ...] = (
    "cv_match_weight",
    "company_mission_fit_weight",
    "role_mission_fit_weight",
    "comp_weight",
    "cultural_weight",
    "red_flags_weight",
)

# Legacy YAML keys → canonical keys. Older profile.yaml files used names
# that semantically mismatched the dimensions they applied to (see
# core/schema.ScoringWeights docstring). On save we silently migrate.
LEGACY_ALIASES: dict[str, str] = {
    "tech_stack_weight": "comp_weight",
    "seniority_weight": "cultural_weight",
    "location_remote_weight": "red_flags_weight",
}


@dataclass(frozen=True)
class WeightUpdate:
    field: str
    value: float


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def profile_path(settings: Settings, profile: str) -> Path:
    return settings.profile_dir(profile) / "profile.yaml"


def update_weights(
    settings: Settings, profile: str, new_weights: dict[str, float]
) -> dict[str, float]:
    """
    Atomically rewrite the `scoring:` block in profile.yaml. Only fields in
    WEIGHT_FIELDS are touched; everything else (including comments) survives.

    Returns the final weight values that were written.
    """
    invalid = set(new_weights) - set(WEIGHT_FIELDS)
    if invalid:
        raise ValueError(f"unknown weight field(s): {sorted(invalid)}")

    for k, v in new_weights.items():
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"{k}={v} out of range [0,1]")

    path = profile_path(settings, profile)
    if not path.exists():
        raise ProfileYamlError(f"profile.yaml not found at {path}")

    yaml = _yaml()
    try:
        with path.open("r", encoding="utf-8") as f:
            data: Any = yaml.load(f)
    except YAMLError as e:
        raise ProfileYamlError(
            f"profile.yaml is malformed; fix the file in your editor and reload: {e}"
        ) from e
    if not isinstance(data, dict):
        raise ProfileYamlError("profile.yaml must be a YAML mapping at the top level")

    scoring = data.setdefault("scoring", {})

    # Migrate any legacy aliases to canonical keys before writing new values.
    # Old YAMLs survive without a manual edit.
    for old_key, new_key in LEGACY_ALIASES.items():
        if old_key in scoring and new_key not in scoring:
            scoring[new_key] = scoring.pop(old_key)
        elif old_key in scoring:
            # Both keys present (rare) — drop the legacy one.
            del scoring[old_key]

    for k, v in new_weights.items():
        scoring[k] = float(v)

    # Atomic write: tmp file in same dir, fsync, rename.
    fd, tmp_path = tempfile.mkstemp(prefix=".profile.", suffix=".yaml.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            yaml.dump(data, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    log.info("updated weights for profile=%s: %s", profile, new_weights)
    return {k: float(scoring[k]) for k in WEIGHT_FIELDS}


# ──────────────────────────────────────────────
# Live re-score preview (item #2)
# ──────────────────────────────────────────────


_TIER_THRESHOLDS = (
    (4.0, "bespoke"),
    (3.0, "template"),
    (2.0, "canonical"),
    (0.0, "skip"),
)


def _tier_for_score(score: float | None) -> str:
    if score is None:
        return "skip"
    for cutoff, tier in _TIER_THRESHOLDS:
        if score >= cutoff:
            return tier
    return "skip"


@dataclass(frozen=True)
class JobDelta:
    job: Job
    old_total: float
    new_total: float
    old_rank: int
    new_rank: int
    old_tier: str
    new_tier: str

    @property
    def score_delta(self) -> float:
        return round(self.new_total - self.old_total, 2)

    @property
    def rank_delta(self) -> int:
        # Positive = moved up (smaller rank number).
        return self.old_rank - self.new_rank

    @property
    def tier_changed(self) -> bool:
        return self.old_tier != self.new_tier


@dataclass(frozen=True)
class RescorePreview:
    top: list[JobDelta]
    total_jobs: int
    tier_changes: int
    biggest_climber: JobDelta | None
    biggest_faller: JobDelta | None


def preview_rescore(
    profile: str, new_weights: ScoringWeights, *, top_n: int = 10
) -> RescorePreview:
    """Recompute totals from cached dimension scores; rank by new total.

    Pure read against the DB — no LLM, no re-rubric, no DB writes.
    Sub-millisecond for hundreds of jobs.
    """
    jobs = [
        j
        for j in db.list_jobs(profile, limit=2000, order_by="total_score DESC")
        if j.total_score is not None
    ]
    if not jobs:
        return RescorePreview(
            top=[], total_jobs=0, tier_changes=0, biggest_climber=None, biggest_faller=None
        )

    new_totals = [(j, weighted_total(j, new_weights)) for j in jobs]
    new_totals.sort(key=lambda t: -t[1])

    old_rank = {j.id: i + 1 for i, j in enumerate(jobs)}
    new_rank = {j.id: i + 1 for i, (j, _) in enumerate(new_totals)}

    deltas: list[JobDelta] = []
    tier_changes = 0
    for j, nt in new_totals:
        old_tier = _tier_for_score(j.total_score)
        new_tier = _tier_for_score(nt)
        if old_tier != new_tier:
            tier_changes += 1
        deltas.append(
            JobDelta(
                job=j,
                old_total=j.total_score or 0.0,
                new_total=round(nt, 2),
                old_rank=old_rank[j.id],
                new_rank=new_rank[j.id],
                old_tier=old_tier,
                new_tier=new_tier,
            )
        )

    # Show top by new score AND highlight movers.
    by_climb = sorted(deltas, key=lambda d: -d.rank_delta)
    biggest_climber = by_climb[0] if by_climb and by_climb[0].rank_delta > 0 else None
    biggest_faller = by_climb[-1] if by_climb and by_climb[-1].rank_delta < 0 else None

    return RescorePreview(
        top=deltas[:top_n],
        total_jobs=len(jobs),
        tier_changes=tier_changes,
        biggest_climber=biggest_climber,
        biggest_faller=biggest_faller,
    )
