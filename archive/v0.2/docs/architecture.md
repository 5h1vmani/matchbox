# Architecture

The big picture in five paragraphs, then the module map, then the data flows.

## Core principles

1. **SSOT** — `people/{name}/profile.yaml` is the only source of truth for candidate facts. The DB is append-only pipeline state, not identity.
2. **Zero-copy handoffs** — Pydantic models flow between modules; no re-serialization at boundaries.
3. **Specialized pipeline > LLM** — Scoring, exclusions, gate checks, and routing are deterministic Python. The LLM is called exactly once per non-canonical application.
4. **One DB per person** — `people/{name}/db.sqlite`. No shared state across profiles. Cross-profile contamination is a class of bug we don't want to debug.
5. **CLI and web are equal partners** — both call the same `matchbox.*` modules. The web layer is a thin adapter over the CLI's primitives. See [decisions/0001](decisions/0001-cli-and-web-as-equal-partners.md).

## Module map

```text
src/matchbox/
├── cli.py                     Typer entry point (scan, tailor, apply, web, ...)
│
├── core/
│   ├── schema.py              All Pydantic models
│   ├── db.py                  SSOT for SQLite — no other module imports sqlite3
│   ├── person.py              load_person(name) -> Person (profile + voice + stories)
│   ├── migrations.py          profile.yaml schema-version chain
│   └── exceptions.py          Typed exceptions
│
├── scoring/
│   ├── exclusions.py          Deterministic sector/visa/comp filtering
│   ├── rubric.py              6-dim heuristic scorer + weighted_total() pure fn
│   └── tier_router.py         total_score → tier + geo inference
│
├── discovery/
│   ├── sources.py             ATSSource dataclass, KNOWN_SOURCES (20+ companies)
│   ├── ats_probe.py           Greenhouse / Ashby / Lever / Workable HTTP probers
│   ├── scan_daily.py          Orchestrate: probe → exclude → score → route → bulk_insert
│   └── scan_funding.py        Funded-company probe
│
├── tailor/
│   ├── gates.py               6 deterministic quality gates
│   ├── anchor_packs.py        Pre-approved bullets by role family
│   ├── content.py             ONE Sonnet call via tool_use → structured JSON
│   ├── render.py              typst compile → PDF (+ canonical builder for 3 geo variants)
│   └── paths.py               Tier dispatch
│
├── outcome/
│   ├── response.py            Log interview/offer/rejection
│   ├── followup.py            Surface stale applied/responded jobs
│   └── analytics.py           Conversion funnel + tier cost summary
│
└── web/                       FastAPI + HTMX + Jinja + Tailwind dashboard
    ├── app.py                 create_app() factory + uvicorn entry
    ├── config.py              Settings dataclass (env-driven, frozen)
    ├── deps.py                FastAPI DI: profile validation, shell context, traversal guard
    ├── filters.py             Jinja filters: usd, score, relative_time, tier_class, ...
    ├── render.py              Single typed render() — toast injection via HX-Trigger header
    ├── tasks.py               In-process background-task tracker (used by bulk tailor)
    ├── tailor_view.py         Web-side adapter over tailor.paths
    ├── profile_view.py        Atomic YAML save + live re-score preview (pure fn)
    ├── demo.py                Idempotent synthetic-data seeder
    └── routes/                One concern per file
        ├── pages.py             Full-page renders: inbox, insights, profile, settings
        ├── jobs.py              Per-job HTMX: rows, detail, star, state, response, JD, tailor
        ├── bulk.py              Selection-bar bulk operations (state, star, tailor + BackgroundTask)
        ├── profile.py           Live re-score preview + atomic save
        ├── palette.py           Cmd+K command palette search
        ├── files.py             Secure PDF/file serving
        └── system.py            Welcome page + demo seed (don't require a profile)
```

## Data flows

### Daily scan

```text
matchbox scan alice
  ↓
discovery/scan_daily.run_daily_scan()
  ↓ probe each ATSSource → list[dict]
  ↓ filter_by_exclusions() → (allowed, excluded)
  ↓ score_job() per allowed job (rubric.py)
  ↓ route_job() → tier
  ↓ bulk_insert_jobs() → people/alice/db.sqlite
```

Returns a `ScanResult` dataclass: `(run_id, raw, inserted, skipped_dupe, excluded, profile)`. The CLI prints a "Next: matchbox web" hint if any jobs were inserted.

### Tailor (single job)

```text
matchbox tailor alice 42      OR     POST /p/alice/jobs/42/tailor
  ↓
tailor/paths.tailor_job(job, person)
  ├── tier=skip       → return None
  ├── tier=canonical  → copy people/alice/output/canonical-{geo}.pdf
  ├── tier=template   → tailor.content.generate_content() (lighter prompt) → gates → typst render
  └── tier=bespoke    → tailor.content.generate_content() (full)           → gates → typst render
  ↓
db.mark_tailored() → state="tailored", paths persisted
```

In the web layer, the tailor flow goes through `web/tailor_view.run()` which wraps `tailor_job` to capture gate violations for visual surfacing in the detail panel.

### Bulk tailor (web)

```text
POST /p/alice/bulk/tailor (after preview + cost confirmation)
  ↓
web/tasks.create() → returns task_id
  ↓
FastAPI BackgroundTasks runs _run_bulk_tailor() in a worker thread
  ↓
For each job: web.tailor_view.run() → web.tasks.update_item()
  ↓
UI polls GET /p/alice/bulk/tailor/{task_id} every 1.5s via HTMX hx-trigger
```

The polling stops when `task.is_terminal == True`.

### Outcome logging

```text
matchbox log-response alice 42 interview
        OR
POST /p/alice/jobs/42/response   (Interview button in detail panel)
  ↓
outcome/response.log_response()
  ↓
db.log_response() inserts into responses table
db.update_job_state() mirrors response_type onto the job row for fast filtering
```

## Scoring dimensions (0–5 scale each)

These are the six dimensions `score_job()` computes and `weighted_total()` recombines. Each one has a matching weight in `ScoringWeights`. **Field names align 1:1.** Older profile.yaml files used different names for the last three; we accept those via `validation_alias` for backward compatibility — see [decisions/0006](decisions/0006-scoring-weight-rename.md).

| Dimension | Scored by | Weight field |
|---|---|---|
| `cv_match_score` | Keyword overlap: JD ∩ (skills + tags) | `cv_match_weight` |
| `company_mission_fit_score` | Dream-tier lookup (tier_1 → 5.0, exploratory → 2.5) | `company_mission_fit_weight` |
| `role_mission_fit_score` | Title keyword match against `targets.primary_roles` | `role_mission_fit_weight` |
| `comp_score` | Placeholder 3.0 today (LLM-assisted scoring planned) | `comp_weight` |
| `cultural_score` | Placeholder 3.0 today | `cultural_weight` |
| `red_flags_score` | 5.0 if no exclusion triggered, 1.0 if triggered | `red_flags_weight` |

Total is `sum(dim * weight)`, capped at 5.0 in practice.

## Voice rule merge

`shared/voice-rules.yaml` provides defaults. `people/{name}/voice.yaml` overrides:

* **Lists** append (unless `key__replace: true`)
* **Maps** replace by key

The merged `VoiceRules` object is passed to `gates.py` for deterministic checks and injected into the LLM prompt via `content.py`.

## Geo variants

Each application targets one of three geo footers: `uk`, `india`, `relocate`. Canonical PDFs are pre-rendered for all three (zero cost at submission). `infer_geo(country)` maps a job's country string to the correct variant.

## Quality gates (`tailor/gates.py`)

| Gate | Trigger |
|---|---|
| `bullet_too_short` | < `min_word_count_cv_bullet` words |
| `bullet_too_long` | > `max_word_count_cv_bullet` words |
| `banned_word` | Word in `voice.banned_words` present |
| `banned_opener` | Cover letter starts with a banned opener |
| `em_dash` | `—` present (if `voice.no_em_dashes: true`) |
| `contraction` | `don't / can't / I'm / ...` (if `voice.no_contractions: true`) |

`gate_mode` controls behaviour:

* `warn` — log violations, continue rendering (default; the operator decides per-job from the visual surface in the web detail panel).
* `raise` — raise `GateFailureError`, no PDF written.
* `skip` — log and return `None`.

## Web architecture

**Server-rendered HTML with HTMX for partials.** No build step, no Node toolchain. See [decisions/0002](decisions/0002-htmx-over-react.md) for the reasoning.

* **Templates** in `web/templates/`. Pages extend `base.html`. Reusable bits prefixed `_`.
* **Tailwind via Play CDN.** `@apply` doesn't work — write rules directly in CSS.
* **Alpine.js** for tiny client state (modal open/close, form sliders). HTMX for everything that talks to the server.
* **HX-Trigger header** for cross-cutting events (`matchbox:toast` is the SSOT for all toasts).
* **Background work** uses `FastAPI BackgroundTasks` + the in-process tracker in `web/tasks.py`. Status survives no restarts; that's acceptable for a single-machine tool.

## Security model

Threat model: **own machine, own network**. Not "untrusted users on the internet". See [decisions/0005](decisions/0005-no-auth-localhost-only.md).

Defenses we *do* have:

* Profile-name path parameter validated by regex `^[a-z][a-z0-9_-]{0,30}$` at the FastAPI layer + dir-exists check in `validate_profile()`.
* File serving restricted to `people/{p}/output/{job_id}/{file.pdf|png}` with double-resolve check against the job's output directory.
* Filename pattern restricted to `*.pdf|*.png`.
* Server-enforced cost confirmation above `MATCHBOX_COST_CONFIRM_USD` for tailor (single + bulk).
* Bulk tailor cap (`MAX_BULK_TAILOR = 5`) bounds runaway cost.
* CLI prints a red warning if `--host` is not loopback.

What we deliberately don't have, with rationale:

* **No auth** — single user on localhost; auth is theatre.
* **No CSRF** — same reason.
* **No rate limiting** — same reason.

## Testing

109 tests at last count. Run with `pytest -q`. Categories:

* `test_schema.py` — Pydantic models, defaults, aliases, coercions.
* `test_scoring.py` — `weighted_total()` math, scoring weight backward compat.
* `test_person.py` — integration: load real demo profile from disk.
* `test_web.py` — FastAPI TestClient: routes, security, filter parsing, palette, bulk tailor, profile editor, accessibility markup, task tracker.

CI runs `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest -v`.
