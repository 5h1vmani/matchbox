# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

* Documentation overhaul for open-source release: README badges, full `docs/` index, decision records (ADRs), troubleshooting guide, development guide, CLI reference.
* `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
* `SECURITY.md` with vulnerability-reporting policy and threat model.
* `.github/` issue + pull-request templates, `CODEOWNERS`, Dependabot config.
* Markdown lint, link check, and typo check in CI and pre-commit.

## [0.3.0] - 2026-04-26

### Added

* New web dashboard: FastAPI + HTMX + Jinja + Tailwind, replacing the v0.2 Streamlit UI.
* Four redesigned UI surfaces — Inbox, Insights, Profile, Settings.
* Cmd+K command palette with keyboard navigation.
* Live re-score preview on the Profile page (sliders for the six scoring weights, top-10 delta table, biggest climber/faller, tier-band-change count).
* Bulk tailor with cumulative cost preview, server-enforced confirmation above threshold, cap at 5 jobs.
* Background-task runner (`web/tasks.py`) with HTMX-polled progress modal.
* Demo profile (`people/demo/`) committed to the repo, plus `matchbox seed-demo` for synthetic data.
* `matchbox web` CLI command with `--host` / `--port` / `--reload` flags.
* Inline PDF preview, full JD lazy-load, response history lazy-load.
* Filter chips with per-chip removal.
* Toast system via `HX-Trigger` header (single SSOT in `web/render.py`).
* Undo for destructive state changes (Discard / Reject / Skip).
* Optimistic star toggle.
* ⌘K palette + `?` keyboard help modal + global progress bar.
* Custom error pages (HTML for browser, plain text for HTMX).
* Accessibility: skip link, semantic landmarks, ARIA on all icon buttons, focus trap inside modals, `aria-live` toast announcements.
* Pre-commit hooks: ruff (lint + format), mypy (mirrors CI), markdownlint, codespell, gitleaks, detect-secrets, custom PII regex, custom people-guard.
* Pure function `weighted_total(job, weights)` in `scoring/rubric.py` for cheap re-ranking from cached dimension scores.

### Changed

* **Schema fix (BREAKING):** `ScoringWeights` field names now align 1:1 with `Job` dimension scores (`comp_weight`, `cultural_weight`, `red_flags_weight`). Old names (`tech_stack_weight`, `seniority_weight`, `location_remote_weight`) still load via Pydantic `validation_alias` for backward compatibility, and are silently migrated to the canonical names on first profile-editor save.
* `pyproject.toml`: removed `streamlit`, added `fastapi`, `uvicorn[standard]`, `python-multipart`.
* CLI `scan` command now suggests "next: matchbox web" when jobs were inserted.

### Fixed

* HTMX trigger syntax (`toggle[target.open] once`, not the broken `from:closest details[open]`).
* `hx-push-url` no longer pushes the partial-endpoint URL into history (server now sends `HX-Push-Url` with the canonical `/inbox` URL).
* Bulk-tailor preview clicks no longer accumulate cards.
* Profile editor "Reset to last saved" now actually resets to the last saved values.
* Malformed `profile.yaml` returns a 400 with an actionable message instead of a 500 stack trace.
* HTMX error responses now surface as red toasts (previously silent).
* Bulk-star toast distinguishes "starred" vs "unstarred" vs "mixed".
* Detail panel `‹` / `›` buttons disable at list boundaries.
* Tailwind `@apply` removed from inline `<style>` (Play CDN doesn't process it).

### Removed

* Streamlit UI (`src/matchbox/ui/`) and the `streamlit` dependency.
* The OOB-swap toast template (replaced by the `HX-Trigger` header pattern).

### Security

* Profile-name path parameter validated by regex + dir-exists check.
* File serving restricted to `people/{p}/output/{id}/{name}.{pdf|png}` with double-resolve guard.
* Server-enforced cost confirmation above `MATCHBOX_COST_CONFIRM_USD` (default $1) for tailor (single + bulk).
* CLI prints a red warning if `matchbox web --host` is set to anything other than loopback.

## [0.2.0] - 2026-04-24

### Added

* v0.2 rebuild: Streamlit dashboard, Pydantic schema, Typer CLI, ATS probers (Greenhouse / Lever / Ashby / Workable), 6-dimension scoring rubric, tier router, quality gates, anchor packs, Typst PDF rendering.
* Per-profile SQLite (`people/{name}/db.sqlite`).
* Conventional commits + pre-commit hooks for lint and security.

### Removed

* v0.1 codebase (archived under `archive/v0.1/`, gitignored).

[Unreleased]: https://github.com/5h1vmani/matchbox/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/5h1vmani/matchbox/releases/tag/v0.3.0
[0.2.0]: https://github.com/5h1vmani/matchbox/releases/tag/v0.2.0
