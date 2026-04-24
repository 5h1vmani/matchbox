# Contributing

## Setup

```bash
pip install -e ".[dev]"
```

## Code standards

- **Python 3.12+** — use `from __future__ import annotations`, structural pattern matching where appropriate
- **ruff** for lint + format: `ruff check src/ tests/` and `ruff format src/ tests/`
- **mypy --strict**: `mypy src/`
- **pytest**: `pytest -q`

All three must pass before committing.

## Commit style

Conventional Commits: `type(scope): description`

```
feat(discovery): add Workday ATS prober
fix(db): correct WAL checkpoint on connection close
docs(setup): add Typst install instructions
chore: bump anthropic to 0.52
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`

## Adding a new ATS

1. Implement `probe_<ats>(source: ATSSource) -> list[dict]` in `ats_probe.py`
2. Add factory function + base URL constant in `sources.py`
3. Add dispatch entry in `probe()` in `ats_probe.py`
4. Add at least one entry to `KNOWN_SOURCES`

## Adding a new scoring dimension

1. Add the field to `ScoringWeights` in `schema.py`
2. Implement the heuristic in `rubric.py → score_job()`
3. Update the weighted sum
4. Add the weight to `shared/rubric.yaml`

## Adding a new person

```bash
matchbox init-profile alice
# Fill in people/alice/profile.yaml
# Write people/alice/stories.md
# Run matchbox scan alice --dry-run
```

## SSOT rules

- `people/{name}/profile.yaml` is the single source of truth for all candidate facts.
- `core/db.py` is the only file that imports `sqlite3`.
- No module other than `core/person.py` reads from `people/*/profile.yaml`.
- No module other than `tailor/content.py` calls the Anthropic API.

## Test conventions

- `tests/test_schema.py` — unit tests for Pydantic models (no I/O)
- `tests/test_person.py` — integration tests that load Shiva's profile from disk
- New tests go in `tests/test_<module>.py`
- Use `scope="module"` fixtures for expensive I/O (profile loading)
- Do not mock `load_person()` in integration tests — the real file is the test fixture
