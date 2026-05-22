# Development guide

How to set up a working dev environment, what to know about the layout, and how to release.

For *what* the project is and *why* it works the way it does, read [architecture.md](architecture.md) and [decisions/](decisions/) first. This doc covers the *how* of working on it.

## One-time setup

```bash
git clone https://github.com/5h1vmani/matchbox.git
cd matchbox
pip install -e ".[dev]"
pre-commit install --install-hooks
```

Optional but useful:

* [uv](https://github.com/astral-sh/uv) for faster installs: `uv sync --dev` instead of pip.
* [Typst](https://typst.app): `brew install typst`. Required for `tailor` and `rebuild-canonicals`.

## The dev loop

```bash
# 1. Get the dashboard running with realistic data.
matchbox seed-demo
matchbox web --reload

# 2. Make changes.
$EDITOR src/matchbox/web/...

# 3. Before committing, run the same checks CI runs.
pre-commit run --all-files

# Or piecewise:
ruff check src/ tests/
ruff format src/ tests/
mypy src/matchbox/
pytest -q
```

`--reload` watches `src/matchbox/web/` for file changes and restarts uvicorn. Templates are picked up automatically (Jinja's auto-reload).

## Project layout (working notes)

See [architecture.md](architecture.md) for the canonical map. The bits you'll touch most:

| Want to change… | Edit… |
|---|---|
| A web page or partial | `src/matchbox/web/templates/` + the matching route in `src/matchbox/web/routes/` |
| What an HTMX endpoint returns | `src/matchbox/web/routes/{jobs,bulk,profile,palette,system}.py` |
| Visual styling (colours, badges) | `src/matchbox/web/filters.py` (`tier_class`, `state_class`, `score_color`) |
| The scoring rubric | `src/matchbox/scoring/rubric.py` — also update `tests/test_scoring.py` |
| A new ATS prober | `src/matchbox/discovery/ats_probe.py` + `sources.py` |
| What data a route receives | `src/matchbox/core/db.py` (the *only* file with `sqlite3` import) |
| The CLI | `src/matchbox/cli.py` |

## Running just one test

```bash
pytest tests/test_web.py -k "TestPalette" -v
pytest tests/test_scoring.py::TestWeightedTotal::test_default_weights_sum -v
```

## Pre-commit hooks

The full list is in `.pre-commit-config.yaml`. By tier:

**Auto-fix (silent, never blocks):**

* `end-of-file-fixer`, `trailing-whitespace`
* `check-yaml`, `check-toml`, `check-json`, `check-merge-conflict`
* `check-added-large-files` (500 KB cap)
* `ruff` (lint with `--fix`) + `ruff-format`
* `markdownlint-cli2` (auto-fixes what it can)
* `codespell` (typos)

**Security (blocks disasters):**

* `detect-secrets` (with baseline)
* `gitleaks`
* Custom `.githooks/pii-scan.sh` (phone + consumer email regex)
* Custom `.githooks/people-guard.sh` (blocks `people/{name}/` commits except `demo`)

**Type/lint mirroring CI:**

* `mypy` against `src/matchbox/`

If any hook fails, fix the underlying issue. Don't `--no-verify`.

## Adding a dependency

We're conservative. Before adding one:

1. Can it be done with the stdlib?
2. Can it be a CDN script (we already do this for HTMX, Alpine, Tailwind)?
3. Is the maintenance load justified by the value?

If yes-then-yes-then-yes, add to `pyproject.toml`:

```toml
dependencies = [
    "...existing...",
    "newpkg>=1.2",
]
```

Then `pip install -e ".[dev]"` to update your local env. Dependabot will keep it bumped.

## Commit style

[Conventional Commits](https://www.conventionalcommits.org). The pre-commit hook doesn't enforce this yet (it's listed as a deferred hook tier in [decisions/0007](decisions/0007-no-strictness-hooks-yet.md)) but reviewers will ask for it.

```text
feat(web): add Cmd+K command palette
fix(scoring): align ScoringWeights with Job dimensions
docs(setup): switch verify-install to seed-demo
```

For non-trivial changes, the commit body should explain the *why*.

## Releasing

Matchbox uses [SemVer](https://semver.org).

1. Update `version` in `pyproject.toml`.
2. Update `CHANGELOG.md` — move `[Unreleased]` items into a new `[X.Y.Z]` section with today's date.
3. Run the full check sequence: `pre-commit run --all-files && pytest -q`.
4. Commit: `chore(release): vX.Y.Z`.
5. Tag: `git tag -s vX.Y.Z -m "vX.Y.Z"` (signed) then `git push origin main --tags`.
6. Create a GitHub release from the tag, paste the relevant `CHANGELOG.md` section as the body.

## Debugging the web layer

```bash
MATCHBOX_DEBUG=1 matchbox web --reload
```

Sets `app.debug = True`, exposes `/api/docs` (FastAPI's auto-Swagger).

For HTMX inspection, your browser devtools' Network tab is the friend — every request shows the `HX-Request: true` header so you can filter it.

## Debugging the CLI

```bash
matchbox scan demo --dry-run --verbose       # DEBUG-level logging
```

For deeper poke-around, `python -m pdb -m matchbox.cli scan demo`.

## How CI runs

`.github/workflows/ci.yml` runs on every push and PR to `main`. The job:

1. Sets up Python 3.12.
2. `uv pip install -e ".[dev]" --system`.
3. `ruff check src/ tests/`.
4. `ruff format --check src/ tests/`.
5. `mypy src/matchbox/`.
6. `pytest tests/ -v`.
7. `markdownlint-cli2 "**/*.md"` (docs lint).
8. `lychee` (link check on all markdown).

If pre-commit passes locally, CI will pass — the hooks mirror the CI checks deliberately.

## Things not to do

* Add `--no-verify` to a `git commit`. Fix the hook failure instead.
* Force-push without `--force-with-lease`.
* Commit anything under `people/` other than the demo profile (the `people-guard.sh` hook will block it).
* Bypass cost confirmation in tests by hardcoding `confirmed=1`. The check exists for a reason; if you're testing a path that needs to bypass it, mock `MATCHBOX_COST_CONFIRM_USD` to `0`.
* Add a Node toolchain. We deliberately use Tailwind Play CDN to avoid one (see [decisions/0002](decisions/0002-htmx-over-react.md)).

## Getting help

* [Discussions](https://github.com/5h1vmani/matchbox/discussions) for "is this a bug or am I doing it wrong?"
* [Issues](https://github.com/5h1vmani/matchbox/issues) for confirmed bugs or features.
* For security issues: don't open a public issue — see [SECURITY.md](../SECURITY.md).
