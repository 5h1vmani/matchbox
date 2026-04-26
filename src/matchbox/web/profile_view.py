"""Profile editor adapter — read & atomically rewrite scoring weights.

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

from matchbox.web.config import Settings

log = logging.getLogger(__name__)

WEIGHT_FIELDS: tuple[str, ...] = (
    "cv_match_weight",
    "company_mission_fit_weight",
    "role_mission_fit_weight",
    "tech_stack_weight",
    "seniority_weight",
    "location_remote_weight",
)


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
        raise FileNotFoundError(path)

    yaml = _yaml()
    with path.open("r", encoding="utf-8") as f:
        data: Any = yaml.load(f)

    scoring = data.setdefault("scoring", {})
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
