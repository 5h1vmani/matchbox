"""Shared types for the discovery layer.

Each poller returns a list of `JobRecord` — a typed, normalized shape.
The runner upserts these into the `job` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AtsType = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "smartrecruiters",
    "recruitee",
    "teamtailor",
    "personio",
    "breezy",
    "jazzhr",
]


@dataclass(slots=True)
class JobRecord:
    """One job as fetched from an ATS, before scoring."""

    ats_type: AtsType
    source_slug: str
    company: str
    title: str
    location: str | None
    url: str  # canonical job URL — must be unique per (ats_type, slug)
    apply_url: str | None
    jd_text: str  # cleaned (no HTML tags) JD body
    posted_at: str | None  # ISO 8601 if the source provides it


class PollerError(Exception):
    """A poller failed in a way the runner should surface to the user."""

    def __init__(self, ats_type: AtsType, slug: str, message: str) -> None:
        super().__init__(f"{ats_type}/{slug}: {message}")
        self.ats_type = ats_type
        self.slug = slug
        self.message = message
