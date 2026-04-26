# 0006. Rename ScoringWeights to align with Job dimensions

* Status: accepted
* Date: 2026-04-26
* Tags: schema, breaking, backward-compat

## Context

The `ScoringWeights` model in `core/schema.py` originally had fields named `tech_stack_weight`, `seniority_weight`, `location_remote_weight`. The `Job` model's dimension scores were named `comp_score`, `cultural_score`, `red_flags_score`. The `score_job()` function paired them like this:

```python
total = (
    cv_match * weights.cv_match_weight                  # 1:1, OK
    + mission_score * weights.company_mission_fit_weight  # 1:1, OK
    + role_mission * weights.role_mission_fit_weight    # 1:1, OK
    + comp * getattr(weights, "tech_stack_weight", 0.20)  # MISMATCHED
    + cultural * getattr(weights, "seniority_weight", 0.10)  # MISMATCHED
    + red_flags * weights.location_remote_weight          # MISMATCHED
)
```

The `getattr` fallback was a smell that someone knew this was wrong. Three of six dimensions were silently weighted by semantically unrelated profile fields.

## Decision

Rename `ScoringWeights` fields to align 1:1 with `Job` dimensions:

| Old name | New name |
|---|---|
| `tech_stack_weight` | `comp_weight` |
| `seniority_weight` | `cultural_weight` |
| `location_remote_weight` | `red_flags_weight` |

The other three fields keep their names (already aligned).

**Backward compatibility:** old `profile.yaml` files using the legacy names continue to load via Pydantic `validation_alias`. On first save through the profile editor, the YAML keys are silently migrated to the canonical names.

## Consequences

**Good:**

* `weighted_total()` is now a clean pure function; no `getattr` smell.
* The profile editor UI labels match the actual dimensions they affect.
* Live re-score preview is now mathematically meaningful — moving "comp_weight" actually moves the comp dimension.
* Test coverage explicitly locks in both old-name loading and new-name behaviour (`tests/test_scoring.py:TestScoringWeightsAliases`).

**Bad:**

* Anyone who hand-wrote a `profile.yaml` with the old names sees a name change after their first profile-editor save. This is the only behaviour the user might notice; no scores change in the process.
* The migration logic in `web/profile_view.py` is non-trivial — it has to handle YAMLs with both old and new keys, preferring the new and dropping the legacy.

## Alternatives considered

* **Add new dimensions to `Job` to match the old weight names** (`tech_stack_score`, `seniority_score`, `location_remote_score`). Rejected — the Job-side names actually describe the underlying signals (red flags = exclusion triggers, cultural = soft signals); they're the right names. The weight side was wrong, not the dimension side.
* **Leave the mismatch and add docs explaining it.** Rejected — the silent semantic shift is exactly the kind of bug we deliberately design against (SSOT principle).
* **Make it a hard breaking change with no alias.** Rejected — even a single user has profile.yaml files in the wild; backward-compat is cheap (one Pydantic alias) and worth it.

## References

* `src/matchbox/core/schema.py:ScoringWeights` — the canonical names.
* `src/matchbox/web/profile_view.py:LEGACY_ALIASES` — the migration map.
* `tests/test_scoring.py:TestScoringWeightsAliases` — locks in both behaviours.
