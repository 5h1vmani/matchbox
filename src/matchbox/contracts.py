"""Pydantic models for the app <-> brain JSON contract.

These models are the SINGLE SOURCE OF TRUTH for the artifacts exchanged
through ``runs/`` and described in ``schemas/*.v1.json``. The JSON Schema
files are GENERATED from these models (``python -m matchbox.contracts``);
do not hand-edit them. ``tests/test_contracts.py`` fails if a committed
schema drifts from the model, and if any known-good payload under ``runs/``
stops validating.

Runtime validation still loads the generated ``schemas/*.v1.json`` and runs
``jsonschema`` over it (the published, language-agnostic contract the brain
writes against). The models add static types at the boundaries and remove
the ``dict[str, Any]`` that used to flow through assemble/polish/jobreqs.

Every constraint here mirrors the original hand-written schema exactly:
``Literal[1]`` -> ``const: 1``; ``extra="forbid"`` -> ``additionalProperties:
false``; ``Field(ge=1)`` -> ``minimum: 1``; ``Field(min_length=1)`` ->
``minLength``/``minItems``; ``Literal[...]`` -> ``enum``.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from matchbox.core.db import PROJECT_ROOT

SCHEMAS_DIR = PROJECT_ROOT / "schemas"
_SCHEMA_ID_BASE = "https://matchbox.local/schemas/"
_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# A positive integer id (1-based), used for bullet/job ids across artifacts.
PosInt = Annotated[int, Field(ge=1)]
# A non-empty string.
NonEmptyStr = Annotated[str, Field(min_length=1)]
# YYYY-MM-DD-NNN run ids, monotonic within a day.
_RUN_ID_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$"

Palette = Literal["slate", "ink", "forest", "claret", "bronze"]
Font = Literal["source-serif", "source-sans", "inter", "atkinson-hyperlegible"]
Proficiency = Literal["working", "fluent", "expert"]
Facet = Literal["role_family", "tech", "seniority", "impact"]
RequirementType = Literal["must-have", "responsibility", "nice"]
JobStatus = Literal["pending", "running", "done", "skipped", "error"]
RunStatus = Literal["queued", "running", "done", "error"]


class StrictModel(BaseModel):
    """Base for every contract model: rejects unknown keys, exactly like the
    hand schemas' ``additionalProperties: false``."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# selection.v1.json  (brain -> core)
# --------------------------------------------------------------------------
class Selection(StrictModel):
    """Written by the brain to pick which verified bullets go on the CV and in \
what order, plus a JD-tailored summary. The deterministic core validates that \
every id is a real verified library bullet (the no-fabrication guarantee lives \
in that check, not in selection being an algorithm), voice-gates the summary, \
enforces the one-page budget, then renders. When no selection file is supplied, \
assemble falls back to the deterministic matcher (offline / no-key path)."""

    model_config = ConfigDict(extra="forbid", title="Matchbox CV selection (brain -> core)")

    schema_version: Literal[1]
    run_id: str
    job_id: PosInt
    selected_bullet_ids: Annotated[list[PosInt], Field(min_length=1)] = Field(
        description=(
            "Verified bullet ids, in the order the brain wants them rendered (within "
            "each role). Each MUST be a verified library bullet; the core rejects any "
            "unknown or unverified id. Trailing ids past the one-page budget are "
            "dropped, lowest-priority first."
        )
    )
    summary: NonEmptyStr = Field(
        description=(
            "JD-tailored summary paragraph. Voice-gated by the core (no em-dashes, no "
            "contractions, no banned words, word count). Truthfulness is the brain's "
            "responsibility, exactly like a cover letter -- only verified facts may appear."
        )
    )
    headline: str | None = Field(
        default=None,
        description=(
            "Optional JD-tailored headline (the line under the name). Voice-gated (hard "
            "rules only, no word cap). When omitted, the profile's default headline is "
            "used. Truthfulness is the brain's responsibility."
        ),
    )
    rationale: str | None = Field(
        default=None,
        description=(
            "Optional one-line note on why this selection. Surfaced in changes.md for "
            "the user's audit; never rendered on the CV."
        ),
    )


# --------------------------------------------------------------------------
# polish.v1.json  (brain -> app)
# --------------------------------------------------------------------------
class PolishItem(StrictModel):
    id: PosInt = Field(
        description=(
            "Bullet id that was selected for this CV. Polishing a non-selected bullet is rejected."
        )
    )
    text: NonEmptyStr = Field(description="New wording. Must satisfy shared/voice-rules.json.")
    original_text: str | None = Field(
        default=None,
        description="Optional: what the brain saw before rephrasing. Surfaced in changes.md.",
    )
    covers: list[str] = Field(
        default_factory=list,
        description=(
            "Must-have keywords this rephrasing was intended to carry. Used to validate intent."
        ),
    )


class Polish(StrictModel):
    """Written by the brain after the CV is assembled and the coverage report \
flags missing keywords. Lists the selected bullets whose wording should be \
rephrased to carry the missing must-have terms. The deterministic side \
validates each new text against shared/voice-rules.json, replaces the bullets \
in cv.json, re-renders cv.pdf, and re-runs the keyword-presence check."""

    model_config = ConfigDict(extra="forbid", title="Matchbox polish payload (brain -> app)")

    schema_version: Literal[1]
    run_id: str
    job_id: PosInt
    polished: Annotated[list[PolishItem], Field(min_length=1)]


# --------------------------------------------------------------------------
# job-requirements.v1.json  (brain)
# --------------------------------------------------------------------------
class RequirementItem(StrictModel):
    type: RequirementType
    text: NonEmptyStr
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Verbatim or near-verbatim phrases from the JD that a literal ATS would search for."
        ),
    )
    variants: list[str] = Field(
        default_factory=list,
        description=(
            "Accepted equivalents for the ATS keyword-presence check (e.g. 'K8s' counts "
            "for 'Kubernetes')."
        ),
    )


class JobRequirements(StrictModel):
    """Written by the brain (via `python -m matchbox.jobreqs save`). Cached in \
job.requirements_json with a model_version tag. The matching pipeline scores \
each library component against each requirement."""

    model_config = ConfigDict(extra="forbid", title="Job requirements extracted from a JD")

    schema_version: Literal[1]
    job_id: PosInt
    model_version: str = Field(
        description=(
            "Identifier for the model/prompt that produced these requirements. Changing "
            "this triggers a clean recompute of cached vectors."
        )
    )
    jd_hash: str | None = Field(
        default=None,
        description=(
            "SHA-256 of the JD text the brain extracted from. Lets the app detect a stale "
            "cache when the JD is edited."
        ),
    )
    requirements: Annotated[list[RequirementItem], Field(min_length=1)]


# --------------------------------------------------------------------------
# work-queue.v1.json  (app -> brain)
# --------------------------------------------------------------------------
class QueueJob(StrictModel):
    job_id: PosInt
    company: NonEmptyStr
    title: NonEmptyStr
    jd_text: NonEmptyStr
    apply_url: str = Field(json_schema_extra={"format": "uri"})
    want_cv: bool
    want_cover: bool
    palette: Palette
    font: Font


class WorkQueue(StrictModel):
    """Written by the app when the user confirms a triage run. Read by the \
brain. One file per run, at runs/<run-id>/work-queue.json."""

    model_config = ConfigDict(extra="forbid", title="Matchbox work-queue (app -> brain)")

    schema_version: Literal[1]
    run_id: str = Field(
        pattern=_RUN_ID_PATTERN, description="YYYY-MM-DD-NNN, monotonic within a day."
    )
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    profile_db: str = Field(description="Path to the SQLite DB, relative to the repo root.")
    jobs: Annotated[list[QueueJob], Field(min_length=1)]


# --------------------------------------------------------------------------
# status.v1.json  (brain -> app)
# --------------------------------------------------------------------------
class StatusJob(StrictModel):
    job_id: PosInt
    cv_status: JobStatus
    cover_status: JobStatus
    cv_path: str | None = None
    cover_path: str | None = None
    gaps: list[str] = Field(
        default_factory=list,
        description="Uncovered must-have requirements. Plain language.",
    )
    notes: str | None = None
    error: str | None = None


class Status(StrictModel):
    """Written and updated by the brain as it processes a run. The app \
file-watches this and re-renders the review screen on every change."""

    model_config = ConfigDict(extra="forbid", title="Matchbox status (brain -> app)")

    schema_version: Literal[1]
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    status: RunStatus
    error: str | None = Field(
        default=None, description="Set only when status == 'error'. Human-readable."
    )
    jobs: list[StatusJob] = Field(default_factory=list)


# --------------------------------------------------------------------------
# ingest.v1.json  (brain -> app)
# --------------------------------------------------------------------------
class Tag(StrictModel):
    facet: Facet
    value: NonEmptyStr


class IngestBullet(StrictModel):
    text: NonEmptyStr
    has_metric: bool = False
    source_file: str | None = None
    tags: list[Tag] = Field(default_factory=list)


class IngestExperience(StrictModel):
    company: NonEmptyStr
    role: NonEmptyStr
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    sort_order: int = 0
    bullets: list[IngestBullet] = Field(default_factory=list)


class IngestProject(StrictModel):
    name: NonEmptyStr
    text: NonEmptyStr
    url: str | None = None
    tags: list[Tag] = Field(default_factory=list)


class IngestSkill(StrictModel):
    name: NonEmptyStr
    category: str | None = None
    proficiency: Proficiency | None = None
    tags: list[Tag] = Field(default_factory=list)


class IngestSummary(StrictModel):
    label: NonEmptyStr
    text: NonEmptyStr
    tags: list[Tag] = Field(default_factory=list)


class IngestAnswer(StrictModel):
    question: NonEmptyStr
    answer: NonEmptyStr
    category: str | None = None
    source_file: str | None = None


class IngestProfile(StrictModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)
    headline: str | None = None


class Ingest(StrictModel):
    """Written by the brain after parsing files in inbox/. Consumed by \
`python -m matchbox.onboarding.ingest_cli`. All rows land with facts_verified \
= false (where the column exists); the user confirms them in the review screen."""

    model_config = ConfigDict(extra="forbid", title="Onboarding ingest payload (brain -> app)")

    schema_version: Literal[1]
    profile: IngestProfile | None = None
    experiences: list[IngestExperience] = Field(default_factory=list)
    projects: list[IngestProject] = Field(default_factory=list)
    skills: list[IngestSkill] = Field(default_factory=list)
    summaries: list[IngestSummary] = Field(default_factory=list)
    answers: list[IngestAnswer] = Field(
        default_factory=list,
        description=(
            "Reusable Q&A the brain found in the inbox (cover notes, screening answers). "
            "Lands unverified; the user confirms at /review."
        ),
    )


# --------------------------------------------------------------------------
# Schema generation
# --------------------------------------------------------------------------
# (model, filename) for every published contract. The brain reads these files;
# the app validates against them at runtime. Generated, never hand-edited.
SCHEMA_REGISTRY: tuple[tuple[type[BaseModel], str], ...] = (
    (Selection, "selection.v1.json"),
    (Polish, "polish.v1.json"),
    (JobRequirements, "job-requirements.v1.json"),
    (WorkQueue, "work-queue.v1.json"),
    (Status, "status.v1.json"),
    (Ingest, "ingest.v1.json"),
)


def _strip_field_titles(node: Any) -> Any:
    """Recursively drop pydantic's auto-generated per-field ``title`` keys.

    Pydantic stamps a ``title`` on every property and ``$def``; the hand schemas
    never had them and they carry no validation meaning. Removing them keeps the
    generated contract readable. The artifact's own top-level title is re-applied
    by ``json_schema_for`` after this runs.

    The ``title`` JSON Schema keyword is always a string, whereas a property whose
    NAME is ``title`` (e.g. a job title) maps to a schema object. Only string
    values are stripped, so a real ``title`` property survives."""
    if isinstance(node, dict):
        return {
            k: _strip_field_titles(v)
            for k, v in node.items()
            if not (k == "title" and isinstance(v, str))
        }
    if isinstance(node, list):
        return [_strip_field_titles(v) for v in node]
    return node


def json_schema_for(model: type[BaseModel], filename: str) -> dict[str, Any]:
    """Generate the published JSON Schema for a contract model.

    Adds the ``$schema``/``$id`` envelope the runtime loader and the brain expect,
    strips pydantic's noisy per-field titles, and restores the artifact title."""
    raw = model.model_json_schema()
    title = raw.get("title", model.__name__)
    body = _strip_field_titles(raw)
    body.pop("title", None)
    out: dict[str, Any] = {
        "$schema": _DRAFT,
        "$id": f"{_SCHEMA_ID_BASE}{filename}",
        "title": title,
    }
    out.update(body)
    return out


def write_schemas() -> list[str]:
    """Regenerate every schemas/*.v1.json from its model. Returns the filenames
    written."""
    written = []
    for model, filename in SCHEMA_REGISTRY:
        path = SCHEMAS_DIR / filename
        text = json.dumps(json_schema_for(model, filename), indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
        written.append(filename)
    return written


if __name__ == "__main__":
    for name in write_schemas():
        print(f"wrote schemas/{name}")
