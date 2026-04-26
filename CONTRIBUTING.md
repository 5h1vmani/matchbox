# Contributing to Matchbox

Thanks for considering a contribution. Matchbox is a personal-tools project that we share publicly because the patterns might be useful to others — every PR is read carefully and we'd rather close one quickly than leave it lingering.

For a quick overview of how the project is laid out, see **[docs/architecture.md](docs/architecture.md)**.

## TL;DR

```bash
git clone https://github.com/5h1vmani/matchbox.git
cd matchbox
pip install -e ".[dev]"
pre-commit install --install-hooks      # one-time

# Make changes, then before committing:
ruff check src/ tests/                   # auto-runs in pre-commit
ruff format src/ tests/
mypy src/matchbox/
pytest -q                                 # 109 tests at last count
```

All four must pass. Pre-commit and CI enforce the same set, so if pre-commit is green, CI will be too.

## Setup

You need Python 3.12+. The dev install pulls in:

* `pytest` + `pytest-asyncio` for tests
* `mypy` (strict mode)
* `ruff` (lint + format)
* `httpx` (used by FastAPI's `TestClient`)

Optional but recommended:

* [uv](https://github.com/astral-sh/uv) for fast resolves: `uv sync --dev`
* [Typst](https://typst.app) for PDF rendering: `brew install typst`. Only needed for `matchbox tailor` and `matchbox rebuild-canonicals`.
* An `ANTHROPIC_API_KEY` env var. Only needed for `tailor`. Scan / score / web all work without it.

Run the dashboard while you develop:

```bash
matchbox seed-demo            # populate people/demo/db.sqlite if empty
matchbox web --reload         # auto-reload on code changes
```

## Code standards

| Tool | Run with | Enforced by |
|---|---|---|
| `ruff check` | lints `src/` and `tests/` | pre-commit + CI |
| `ruff format` | formats `src/` and `tests/` | pre-commit + CI |
| `mypy --strict` | checks `src/matchbox/` | pre-commit + CI |
| `pytest` | runs `tests/` | CI |
| `markdownlint` | lints all `*.md` | pre-commit + CI |
| `codespell` | typo check | pre-commit + CI |

Full ruff config is in `pyproject.toml`. We pick a small but strict ruleset (`E`, `F`, `I`, `UP`, `B`, `SIM`).

## Commit style

We follow [Conventional Commits](https://www.conventionalcommits.org):

```text
feat(scope): description
fix(scope): description
docs: description
chore: description
refactor: description
test: description
perf: description
```

Examples from the repo history:

```text
feat(web): add Cmd+K command palette with keyboard navigation
fix(a11y): focus trap inside modals (palette, help, bulk-tailor)
docs(setup): switch verify-install to seed-demo (shiva is gitignored)
chore: align ScoringWeights with Job dimensions + 4 broken-on-arrival bugs
```

Multi-line commit messages are encouraged for non-trivial changes — explain the *why*, not just the *what*.

## SSOT rules

These are non-negotiable; PRs that violate them will be asked to refactor.

* `people/{name}/profile.yaml` is the single source of truth for candidate facts.
* `core/db.py` is the only file that imports `sqlite3`.
* No module other than `core/person.py` reads from `people/*/profile.yaml`.
* No module other than `tailor/content.py` calls the Anthropic API.
* All currency / score / date formatting goes through `web/filters.py` Jinja filters.
* All HTML responses go through `web/render.py:render()`. Never call `TemplateResponse` directly.
* All toast notifications go through `render(toast=...)`. No OOB swap toast templates.

## Adding things

### A new ATS prober

1. Implement `probe_<ats>(source: ATSSource) -> list[dict]` in `discovery/ats_probe.py`.
2. Add factory function + base URL constant in `discovery/sources.py`.
3. Add a dispatch entry in `probe()` in `discovery/ats_probe.py`.
4. Add at least one entry to `KNOWN_SOURCES` so the new prober is exercised in scans.
5. Add a test in `tests/test_discovery.py`.

### A new scoring dimension

1. Add the field to `Job` in `core/schema.py` and write a migration in `core/migrations.py` if persisted.
2. Add a corresponding weight to `ScoringWeights` in `core/schema.py`.
3. Implement the heuristic in `scoring/rubric.py:score_job()`.
4. Update `weighted_total()` to include the new dimension.
5. Update the profile editor template + form handler (`web/templates/pages/profile.html`, `web/routes/profile.py`).
6. Update `tests/test_scoring.py`.
7. Document the dimension in `docs/architecture.md` ("Scoring dimensions" table).

### A new web route

1. Decide which router file owns it — see `web/routes/` (one concern per file: `pages`, `jobs`, `bulk`, `profile`, `palette`, `files`, `system`).
2. Use `ProfileDep` for any route that takes a profile name. This validates against the directory pattern + dir-exists check.
3. Use `web/render.py:render()` for HTML; never `TemplateResponse` directly.
4. Add a smoke test in `tests/test_web.py` covering happy path + at least one error case.

### A new person profile

```bash
matchbox init-profile alice
$EDITOR people/alice/profile.yaml
$EDITOR people/alice/stories.md
matchbox scan alice --dry-run
```

`people/alice/` is auto-gitignored; only `people/demo/` is committed.

## Testing conventions

* `tests/test_schema.py` — unit tests for Pydantic models (no I/O).
* `tests/test_scoring.py` — scoring rubric + `weighted_total` (deterministic).
* `tests/test_person.py` — integration: load demo profile from disk.
* `tests/test_web.py` — FastAPI TestClient against the demo profile (force-seeded in a fixture).
* New tests go in `tests/test_<module>.py`.
* Use `scope="module"` fixtures for expensive I/O (profile loading, DB seed).
* Don't mock `load_person()` in integration tests — the real demo file is the test fixture.
* If your test needs to write to `people/demo/profile.yaml`, use the `demo_yaml_backup` fixture pattern that snapshots and restores.

## Documentation

Docs live with the code (`docs/`) and are reviewed in PRs. If you change behaviour, update the relevant doc(s) in the same PR. Markdown is linted with `markdownlint`; a pre-commit hook will catch mistakes.

For architectural decisions, add an ADR to `docs/decisions/`. See the existing ones for the format.

## Pull request flow

1. Fork the repo or create a feature branch (`feat/...`, `fix/...`, `docs/...`).
2. Make your changes — small, focused PRs are easier to review.
3. Make sure pre-commit passes (`pre-commit run --all-files`).
4. Push and open a PR using the template.
5. We'll review within a few days. Feedback is direct; don't read brusqueness as hostility.

## What we won't merge

* Code that breaks SSOT rules above.
* Changes that add dependencies without a clear payoff. (Tailwind is via CDN; we don't want a Node toolchain.)
* New web frameworks (Django, Flask). The HTMX choice is documented in `docs/decisions/`.
* Changes that disable the security defaults (`127.0.0.1` binding, server-enforced cost confirmation).
* Bulk PRs that mix unrelated concerns.

If you're unsure whether something fits, open a discussion or a draft PR and ask.

## Code of conduct

By participating you agree to abide by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
