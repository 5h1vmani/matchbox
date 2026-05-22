"""Web app configuration — environment-driven, single source of truth."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    people_dir: Path
    static_dir: Path
    templates_dir: Path
    default_profile: str | None
    cost_confirm_threshold_usd: float
    debug: bool

    @classmethod
    def load(cls) -> Settings:
        root = _repo_root()
        web_dir = Path(__file__).resolve().parent
        return cls(
            repo_root=root,
            people_dir=root / "people",
            static_dir=web_dir / "static",
            templates_dir=web_dir / "templates",
            default_profile=os.getenv("MATCHBOX_PROFILE"),
            cost_confirm_threshold_usd=float(os.getenv("MATCHBOX_COST_CONFIRM_USD", "1.0")),
            debug=os.getenv("MATCHBOX_DEBUG", "0") == "1",
        )

    def profile_dir(self, profile: str) -> Path:
        return self.people_dir / profile

    def output_dir(self, profile: str, job_id: int) -> Path:
        return self.profile_dir(profile) / "output" / str(job_id)
