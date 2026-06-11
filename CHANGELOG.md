# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.4.0] - 2026-06-11

### Added

* **v1.2 honest core (backend).** Discovery serializes real salary and reads coverage from the tailoring artifact; a deterministic `role_family` tagger un-deads salary role-scoping. `coverage.json` gains a three-state `band` (covered/partial/uncovered, partial keying off `facts_verified`) and an `evidence_bullet_id`.
* **BYOK live layer (optional, additive to the manual handoff).** `GET /api/library/facts` (verified grounding), `POST /api/voice-check` (form only, prose-scoped tiers), `POST /api/ai/stream` (localhost SSE proxy to the user's Anthropic/OpenAI key; the app still holds no LLM client), `GET/POST/DELETE /api/ai/{config,key}`. The provider key lives in a `0600` file beside the profile DB, never in the browser.
* **Answer library** (migration 008): reusable Q&A with the `facts_verified` gate and `used_count`, `/api/answers`, and ingest support.
* **Interview loop** (migration 009): `interview_round` + `debrief`, `/api/applications/{id}/rounds` + `/api/rounds/{id}` + one-tap debrief; prep agent-tasks carry prior debriefs as assisted context.
* **Momentum coach + rejection learning**: `/api/insights/momentum` (real weekly pace + rest/healthy/push threshold) and structured `close_reason` (migration 010) with a deterministic category rollup (`/api/insights/rejection-reasons`).
* **Offers**: own-pool benchmark gains an honest p25–p75 `range` and a `basis` line.
* **Frontend**: ⌘K command palette, BYOK Settings, momentum/rejection panels, and Library Answers / Workspace (interview loop) / Offers screens.
* **All-React UI.** The Jinja/HTMX pages (Library, Profile, Sources, onboarding/Intake, Review, Apply packet, run progress) are now React screens over a JSON-only API; a SPA catch-all serves the app for every non-`/api` route. The retired Jinja routes + templates are moved to `archive/jinja/`.
* Documentation overhaul for open-source release: README badges, full `docs/` index, decision records (ADRs), troubleshooting guide, development guide, CLI reference.
* `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
* `SECURITY.md` with vulnerability-reporting policy and threat model.
* `.github/` issue + pull-request templates, `CODEOWNERS`, Dependabot config.
* Markdown lint, link check, and typo check in CI and pre-commit.
* **Apply-ready tracker.** Every application row, board card, and the detail drawer link to the job posting and the tailored CV. New sandboxed route `GET /api/applications/{id}/cv`; when `cv_path` is unset the serializer falls back to the newest run output on disk.
* **Tailor from the tracker.** Saved roles without a CV get a one-click "Tailor a CV" action (row and drawer) that queues a run and surfaces the handoff prompt; queued-but-undrafted roles show the copyable `process run` command instead.
* **Skills selection in the brain contract.** `selected_skill_ids` in `selection.v1.json`: the brain picks role-relevant skills, and without it a JD-matched fallback caps the section. The full library is never dumped. changes.md reports `Skills: N of M rendered`.
* **Deliberate page count.** `target_pages` (1 or 2) in the selection scales the bullet budget; changes.md reports `Pages: N (target M)`. The rubric gains a page-discipline rule: one page tight, or two pages full.
* **Readable drafts.** The detail drawer shows follow-up and thank-you draft bodies with a Copy button; marking sent also updates the artifact status.
* **Mobile and accessibility pass.** Top-bar nav under 760px, grid overflow fixes on Browse/Insights/Workspace, touch-visible actions, keyboard focus parity, WCAG AA contrast, aria-live toasts.
* URL/history sync with per-screen titles, loading states on every store, and a favicon (the brand matchstick).
* Apply packet: Open PDF and Download buttons, "Open posting" on the Submit tab, and a recoverable `process run` command with Copy.

### Changed

* The CV header renders the tailored headline as its own bold line under the name.
* Metric emphasis bolds signal only: currency, percentages, multipliers, magnitudes, and counts. Years and version numbers are no longer bold.
* Profile links on the CV are scheme-safe (no doubled `https://`), and extra links render instead of being dropped.
* Honest copy: "Mark sent" instead of "Send"; deleting an experience and "Verify everything" now ask for confirmation.
* Toast Undo reverts the decision on the server, not just in the UI.

### Removed

* The Apply screen's palette/font restyle controls (the renderer ignored them by design).

### Fixed

* The Browse roles grid no longer overflows the viewport with no scrollbar.

## [0.3.0] - 2026-04-26

### Added

* New web dashboard: FastAPI + HTMX + Jinja + Tailwind, replacing the v0.2 Streamlit UI.
* Four redesigned UI surfaces: Inbox, Insights, Profile, Settings.
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
