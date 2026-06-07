# Contributing to Matchbox

Thanks for considering a contribution. Matchbox is a personal-tools project that we share publicly because the patterns might be useful to others — every PR is read carefully and we'd rather close one quickly than leave it lingering.

For a quick overview of how the project is laid out, see the **Architecture** section of the [README](README.md#architecture-one-screen), or the deeper [docs/v1-engineering-spec.md](docs/v1-engineering-spec.md).

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
pytest -q                                 # 326 passed, 3 skipped at last count
```

All four must pass. Pre-commit and CI enforce the same set, so if pre-commit is green, CI will be too.

## Setup

You need Python 3.12 or 3.13 — CI runs both in a matrix, so target either. The
dev install pulls in:

* `pytest` + `pytest-asyncio` for tests
* `mypy` (strict mode)
* `ruff` (lint + format)
* `httpx` (used by FastAPI's `TestClient`)
* `weasyprint` (>=60) for HTML-to-PDF rendering. It needs Pango and Cairo
  system libraries at runtime — on macOS `brew install pango` covers it; on
  Debian/Ubuntu install `libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0
  libcairo2` (see the apt step in `.github/workflows/ci.yml`).

Optional but recommended:

* [uv](https://github.com/astral-sh/uv) for fast resolves: `uv sync --dev`

The core CLIs (`matchbox`, `matchbox-web`, `matchbox-ingest`,
`matchbox-assemble`, `matchbox-jobreqs`) need no API key — there is no
in-process LLM client. The AI reasoning is a manual handoff: the app queues
typed intents and surfaces a "process run `<id>`" prompt you paste into Claude
Code, which drains the queue and runs `matchbox-assemble`.

Build the React SPA once, then run the dashboard while you develop:

```bash
cd frontend && npm install && npm run build   # builds the SPA the server serves
matchbox-web                                   # serve on 127.0.0.1:8765
```

`matchbox web` is the same server (it accepts only `--host`/`--port`). For
frontend iteration use `npm run dev` from `frontend/` — Vite proxies `/api`
to the running server. The server returns HTTP 503 ("SPA not built") if the
build output is missing.

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
fix(discovery): mask the Adzuna app_key in GET /api/sources
chore(deps): pin ruff and bump the toolchain to latest
ci: declare weasyprint dependency + install its system libs
```

Multi-line commit messages are encouraged for non-trivial changes — explain the *why*, not just the *what*.

## SSOT rules

These are non-negotiable; PRs that violate them will be asked to refactor.

* One SQLite database per profile (`people/<slug>/matchbox.db`) is the single
  source of truth for candidate facts. The active profile is chosen by
  `MATCHBOX_PROFILE` (or an explicit `MATCHBOX_DB` path).
* `core/db.py` owns the connection layer — `db_path()`, `connect()`, and the
  `transaction()` context manager. Code that touches the DB connects through
  those helpers rather than opening its own path.
* The web layer is a JSON API: routes under `web/routes/*_api.py` return JSON,
  and the React SPA in `frontend/` consumes `/api/*`. No HTML is rendered
  server-side for the live UI (the retired Jinja/HTMX templates are archived
  under `archive/jinja/`).
* The app holds no in-process LLM client and calls no model API. All AI work
  is a manual handoff through the `agent_task` queue and
  `runs/<id>/work-queue.json`.

## Adding things

### A new ATS poller

Direct-from-ATS sources live in `discovery/pollers.py`. Implement a
`poll_<ats>(...)` function that returns `JobRecord`s (the dataclass in
`discovery/base.py`) and register it in the `POLLERS` dispatch dict at the
bottom of the file. Job-board aggregators are the parallel case in
`discovery/aggregators.py` (the `AGGREGATORS` dict). The scan runner in
`discovery/runner.py` drives both, and `discovery/enrich.py` parses the raw
records into structured fields. Add coverage in `tests/test_discovery.py` or
`tests/test_aggregators.py`.

### A new scoring dimension

The rubric is data-driven: dimension names, descriptions, and
`default_weight`s live in `shared/rubric.json`, loaded by
`scoring/rubric.py:load_rubric()` (so weights are tunable without code edits).
To add a dimension, declare it there, implement its per-dimension scorer in
`scoring/rubric.py`, and wire it into `score_job()`. If it needs persisted
inputs, add a column via a new `core/migrations.py` step and the matching model
in `core/models.py`. Update `tests/test_scoring.py`.

### A new web route

1. Routes live in `web/routes/`, one concern per file. JSON API routers are the
   `*_api.py` files (e.g. `profile_api.py`, `targets_api.py`); they return JSON,
   not HTML.
2. Register the router with `app.include_router(...)` in `web/app.py`.
3. Surface it in the React SPA under `frontend/src/` (a screen in
   `frontend/src/screens/` plus its `/api` call).
4. Add a smoke test alongside the existing web tests (for example
   `tests/test_ai_web.py`, `tests/test_review_run_web.py`,
   `tests/test_library_crud_web.py`) covering the happy path and at least one
   error case.

### A new person profile

Profiles are SQLite-per-profile, selected by the `MATCHBOX_PROFILE`
environment variable (or an explicit `MATCHBOX_DB` path). Onboard through the
SPA (drop files, then ingest) or by feeding a payload to `matchbox-ingest`:

```bash
MATCHBOX_PROFILE=alice matchbox-ingest --file payload.json
```

The DB lands at `people/alice/matchbox.db`. `people/alice/` is auto-gitignored;
only `people/demo/` is committed.

## Testing conventions

* `tests/test_data_layer.py` — the core models + DB layer.
* `tests/test_migrations.py` — schema migrations.
* `tests/test_scoring.py` — the scoring rubric and `score_job()` (deterministic).
* `tests/test_discovery.py` / `tests/test_aggregators.py` — pollers and aggregators.
* Web routes are covered by the `*_web.py` suites (for example
  `tests/test_ai_web.py`, `tests/test_review_run_web.py`,
  `tests/test_library_crud_web.py`) using FastAPI's `TestClient`.
* New tests go in `tests/test_<module>.py`.
* For anything that touches the database, use the `tmp_db` fixture in
  `tests/conftest.py`: it builds a migrated, isolated SQLite DB at
  `tmp_path/matchbox.db` (`connect(...)` then `migrate(...)`) — one fresh DB per
  test, no shared on-disk state.

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
* Changes that add dependencies without a clear payoff. The live UI is a
  React + Vite + TypeScript SPA under `frontend/` with its own Node build; new
  frontend dependencies still need to earn their place. (The earlier project
  history ran an HTMX + Tailwind-via-CDN, no-Node UI — see `docs/decisions/`;
  it now lives, retired, under `archive/jinja/`.)
* New backend web frameworks (Django, Flask). The FastAPI JSON-API choice is
  documented in `docs/decisions/`.
* Changes that disable the security defaults (`127.0.0.1` binding, server-enforced cost confirmation).
* Bulk PRs that mix unrelated concerns.

If you're unsure whether something fits, open a discussion or a draft PR and ask.

## Code of conduct

By participating you agree to abide by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
