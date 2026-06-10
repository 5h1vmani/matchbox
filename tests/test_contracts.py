"""The pydantic contract models are the source of truth for schemas/*.v1.json.

Two gates:
  * sync     - every committed schema equals what its model emits, so a model
               edit without `python -m matchbox.contracts` fails CI (no drift).
  * corpus   - representative known-good payloads validate against BOTH the
               committed schema (the runtime jsonschema path) and the model,
               and known-bad payloads are rejected by both (strictness held).

The corpus is inline here on purpose: the real payloads live under runs/, which
is gitignored and absent in CI.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from matchbox import contracts as c

# One representative valid payload per artifact, keyed by schema filename.
VALID: dict[str, tuple[type[Any], dict[str, Any]]] = {
    "selection.v1.json": (
        c.Selection,
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "job_id": 42,
            "selected_bullet_ids": [3, 1, 2],
            "selected_project_ids": [2, 1],
            "summary": "Engineer with a verified delivery record across two roles.",
            "headline": "Senior Backend Engineer",
            "rationale": "covers the three must-haves",
        },
    ),
    "polish.v1.json": (
        c.Polish,
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "job_id": 42,
            "polished": [
                {
                    "id": 3,
                    "text": "Built data pipelines on kubernetes.",
                    "original_text": "Built data pipelines.",
                    "covers": ["kubernetes"],
                }
            ],
        },
    ),
    "job-requirements.v1.json": (
        c.JobRequirements,
        {
            "schema_version": 1,
            "job_id": 42,
            "model_version": "reqs-v1",
            "jd_hash": "deadbeef",
            "requirements": [
                {
                    "type": "must-have",
                    "text": "5 years of Python",
                    "keywords": ["python"],
                    "variants": ["py"],
                }
            ],
        },
    ),
    "work-queue.v1.json": (
        c.WorkQueue,
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "created_at": "2026-05-22T10:00:00Z",
            "profile_db": "people/demo/matchbox.db",
            "jobs": [
                {
                    "job_id": 1,
                    "company": "Acme",
                    "title": "Backend Engineer",
                    "jd_text": "Build and operate services.",
                    "apply_url": "https://acme.test/jobs/1",
                    "want_cv": True,
                    "want_cover": False,
                    "palette": "slate",
                    "font": "source-serif",
                }
            ],
        },
    ),
    "status.v1.json": (
        c.Status,
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "status": "running",
            "jobs": [
                {
                    "job_id": 1,
                    "cv_status": "done",
                    "cover_status": "skipped",
                    "cv_path": "runs/2026-05-22-001/output/1/cv.pdf",
                    "cover_path": None,
                    "gaps": ["JD asks for Terraform; no verified component covers it"],
                    "notes": "Selected 9 bullets.",
                    "error": None,
                }
            ],
        },
    ),
    "job-facts.v1.json": (
        c.JobFacts,
        {
            "schema_version": 1,
            "job_id": 7558,
            "salary_min": 3500000,
            "salary_max": 5000000,
            "salary_currency": "INR",
            "salary_period": "year",
            "employment_type": "full_time",
            "seniority": "senior",
            "min_years_exp": 5,
            "role_family": "ai-transformation",
            "remote_scope": "remote (India only)",
            "country": "in",
            "sponsorship": "unknown",
            "citizenship_required": False,
            "clearance_required": False,
            "closes_at": "2026-07-01",
        },
    ),
    "ingest.v1.json": (
        c.Ingest,
        {
            "schema_version": 1,
            "profile": {
                "full_name": "Test User",
                "email": "test@example.com",
                "links": ["https://example.test/u"],
            },
            "experiences": [
                {
                    "company": "Acme",
                    "role": "Engineer",
                    "start_date": "2020",
                    "end_date": None,
                    "location": "Remote",
                    "sort_order": 0,
                    "bullets": [
                        {
                            "text": "Shipped the billing service.",
                            "has_metric": False,
                            "source_file": "cv.pdf",
                            "tags": [{"facet": "tech", "value": "python"}],
                        }
                    ],
                }
            ],
            "skills": [
                {"name": "Python", "category": "language", "proficiency": "expert", "tags": []}
            ],
        },
    ),
}

# Known-bad payloads: (filename, payload, why). Each must be rejected by both the
# committed schema and the model, proving the generated schema keeps the original
# strictness.
INVALID: list[tuple[str, dict[str, Any], str]] = [
    (
        "selection.v1.json",
        {
            "schema_version": 1,
            "run_id": "r",
            "job_id": 1,
            "selected_bullet_ids": [1],
            "summary": "ok",
            "surprise": "extra",
        },
        "additionalProperties: false",
    ),
    (
        "selection.v1.json",
        {
            "schema_version": 1,
            "run_id": "r",
            "job_id": 1,
            "selected_bullet_ids": [],
            "summary": "x",
        },
        "selected_bullet_ids minItems: 1",
    ),
    (
        "polish.v1.json",
        {"schema_version": 1, "run_id": "r", "job_id": 1, "polished": []},
        "polished minItems: 1",
    ),
    (
        "status.v1.json",
        {"schema_version": 1, "run_id": "2026-05-22-001", "status": "not-a-status", "jobs": []},
        "status enum",
    ),
    (
        "work-queue.v1.json",
        {
            "schema_version": 1,
            "run_id": "2026-05-22-001",
            "created_at": "2026-05-22T10:00:00Z",
            "profile_db": "x",
            "jobs": [
                {
                    "job_id": 1,
                    "company": "Acme",
                    "jd_text": "build",
                    "apply_url": "https://a.test",
                    "want_cv": True,
                    "want_cover": False,
                    "palette": "slate",
                    "font": "inter",
                }
            ],
        },
        "job missing required 'title'",
    ),
    (
        "job-requirements.v1.json",
        {
            "schema_version": 1,
            "job_id": 1,
            "model_version": "v1",
            "requirements": [{"type": "bogus", "text": "x"}],
        },
        "requirement type enum",
    ),
    (
        "ingest.v1.json",
        {"schema_version": 1, "experiences": [{"company": "X"}]},
        "experience missing required 'role'",
    ),
    (
        "selection.v1.json",
        {
            "schema_version": 2,
            "run_id": "r",
            "job_id": 1,
            "selected_bullet_ids": [1],
            "summary": "x",
        },
        "schema_version const: 1",
    ),
    (
        "selection.v1.json",
        {
            "schema_version": 1,
            "run_id": "r",
            "job_id": 1,
            "selected_bullet_ids": [1],
            "selected_project_ids": [],
            "summary": "x",
        },
        "selected_project_ids minItems: 1 when present",
    ),
    (
        "job-facts.v1.json",
        {"schema_version": 1, "job_id": 1, "employment_type": "permanent"},
        "employment_type enum",
    ),
    (
        "job-facts.v1.json",
        {"schema_version": 1, "job_id": 1, "country": "India"},
        "country must be lowercase ISO-2",
    ),
]


def _committed(filename: str) -> dict[str, Any]:
    return json.loads((c.SCHEMAS_DIR / filename).read_text(encoding="utf-8"))


def test_committed_schemas_match_models() -> None:
    for model, filename in c.SCHEMA_REGISTRY:
        assert c.json_schema_for(model, filename) == _committed(filename), (
            f"{filename} is out of sync with its model; run `python -m matchbox.contracts`"
        )


def test_registry_covers_every_schema_file() -> None:
    on_disk = {p.name for p in c.SCHEMAS_DIR.glob("*.v1.json")}
    in_registry = {filename for _, filename in c.SCHEMA_REGISTRY}
    assert on_disk == in_registry


@pytest.mark.parametrize("filename", list(VALID))
def test_valid_payload_passes_schema_and_model(filename: str) -> None:
    model, payload = VALID[filename]
    errors = [e.message for e in Draft202012Validator(_committed(filename)).iter_errors(payload)]
    assert errors == [], f"{filename}: {errors}"
    model.model_validate(payload)  # the source of truth must accept it too


@pytest.mark.parametrize(("filename", "payload", "why"), INVALID)
def test_invalid_payload_rejected_by_schema_and_model(
    filename: str, payload: dict[str, Any], why: str
) -> None:
    schema_errors = list(Draft202012Validator(_committed(filename)).iter_errors(payload))
    assert schema_errors, f"{filename}: committed schema accepted bad payload ({why})"
    model = VALID[filename][0]
    with pytest.raises(ValidationError):
        model.model_validate(payload)
