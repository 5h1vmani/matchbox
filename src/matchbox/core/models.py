"""Internal dataclasses mirroring the SQLite tables.

Dataclasses (not pydantic) for internal rows: cheap, immutable, no validation
overhead. Pydantic is reserved for the schema boundary (work-queue / status /
job-requirements JSON).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ItemType = Literal["bullet", "project", "skill", "summary_variant"]
Facet = Literal["role_family", "tech", "seniority", "impact"]
Proficiency = Literal["working", "fluent", "expert"]


@dataclass(slots=True)
class Experience:
    id: int
    company: str
    role: str
    start_date: str | None
    end_date: str | None
    location: str | None
    sort_order: int


@dataclass(slots=True)
class Bullet:
    id: int
    experience_id: int
    text: str
    has_metric: bool
    facts_verified: bool
    source_file: str | None
    created_at: str


@dataclass(slots=True)
class Project:
    id: int
    name: str
    text: str
    url: str | None
    facts_verified: bool


@dataclass(slots=True)
class Skill:
    id: int
    name: str
    category: str | None
    proficiency: Proficiency | None


@dataclass(slots=True)
class SummaryVariant:
    id: int
    label: str
    text: str


@dataclass(slots=True)
class Tag:
    id: int
    facet: Facet
    value: str


@dataclass(slots=True)
class TaggedItem:
    """A library item paired with its tags. Used by list views in M1+."""

    kind: ItemType
    item: Bullet | Project | Skill | SummaryVariant
    tags: list[Tag] = field(default_factory=list)
