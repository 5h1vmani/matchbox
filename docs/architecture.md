# Architecture

## Core principles

1. **SSOT** — `profile.yaml` is the only source of truth for candidate facts. The DB is append-only pipeline state, not identity.
2. **Zero-copy handoffs** — Pydantic models flow between modules; no re-serialization.
3. **Specialized pipeline > LLM** — Scoring, exclusions, gate checks, and routing are deterministic Python. LLM is called exactly once per non-canonical application.
4. **One DB per person** — `people/{name}/db.sqlite`. No shared state across profiles.

## Module map

```
core/
  schema.py      All Pydantic models (Profile, Job, VoiceRules, Application, ...)
  db.py          SSOT for all SQLite reads/writes — no other module uses sqlite3
  person.py      load_person() → Person (profile + voice + stories)
  migrations.py  profile.yaml schema version chain
  exceptions.py  Typed exceptions (ProfileNotFoundError, GateFailureError, ...)

scoring/
  exclusions.py  Deterministic sector exclusion (no LLM)
  rubric.py      6-dimension heuristic scorer (no LLM)
  tier_router.py Score → bespoke/template/canonical/skip + geo inference

discovery/
  sources.py     ATSSource dataclass, factory fns, KNOWN_SOURCES (20+ companies)
  ats_probe.py   Greenhouse / Ashby / Lever HTTP probers
  scan_daily.py  Orchestrate: probe → exclude → score → route → bulk_insert
  scan_funding.py Funded-company probe (dict-driven, KNOWN_SOURCES fallback)

tailor/
  gates.py       6 deterministic quality gates (no LLM)
  anchor_packs.py Pre-approved bullets by role family
  content.py     ONE claude-sonnet call via tool_use → structured JSON
  render.py      typst compile → PDF (+ canonical builder)
  paths.py       Tier dispatch: bespoke/template → LLM+render; canonical → copy

outcome/
  response.py    Log interview/offer/rejection → mirrors job state in DB
  followup.py    Surface stale applied/responded jobs
  analytics.py   Conversion funnel + tier cost summary

ui/
  ui.py          Streamlit dashboard (pipeline, analytics, follow-ups, scan history)

cli.py           Typer entry point (scan, tailor, apply, score-job, log-response, ...)
```

## Data flow

```
matchbox scan shiva
  ↓
discovery/scan_daily.py
  ↓ probe each ATSSource → list[dict]
  ↓ filter_by_exclusions() → (allowed, excluded)
  ↓ score_job() per allowed job (rubric.py)
  ↓ route_job() → tier
  ↓ bulk_insert_jobs() → db.sqlite

matchbox tailor shiva 42
  ↓
tailor/paths.py (dispatch by tier)
  ├── canonical: copy pre-rendered PDF
  ├── template:  anchor_packs + content.generate_content + gates + render
  └── bespoke:   content.generate_content (full) + gates + render
  ↓
db.mark_tailored() → job.state = "tailored"

matchbox log-response shiva 42 interview
  ↓
outcome/response.py → db.log_response() + db.update_job_state()
```

## Scoring dimensions (0–5 scale each)

| Dimension | Method | Default weight |
|-----------|--------|---------------|
| cv_match | Keyword overlap: JD ∩ (skills + tags) | 0.25 |
| company_mission_fit | Dream tier lookup | 0.15 |
| role_mission_fit | Title keyword match | 0.15 |
| tech_stack / comp | Placeholder → 3.0 | 0.20 |
| cultural / seniority | Placeholder → 3.0 | 0.10 |
| red_flags / location | 5.0 if no exclusion, 1.0 if triggered | 0.15 |

Total is a weighted sum, max = 5.0.

## Voice rule merge

`shared/voice-rules.yaml` provides defaults.
`people/{name}/voice.yaml` overrides:
- **Lists** append (unless `key__replace: true`)
- **Maps** replace by key

The merged `VoiceRules` object is passed to gates.py and injected into the LLM prompt via content.py.

## Geo variants

Each application targets one of three geo footers: `uk`, `india`, `relocate`.
Canonical PDFs are pre-rendered for all three (zero cost at submission).
`infer_geo(country)` maps the job's country string to the correct variant.

## Quality gates (tailor/gates.py)

1. `bullet_too_short` — < `min_word_count_cv_bullet` words
2. `bullet_too_long`  — > `max_word_count_cv_bullet` words
3. `banned_word`      — presence of any word in `voice.banned_words`
4. `banned_opener`    — cover starts with a banned opener
5. `em_dash`          — `—` character present (if `no_em_dashes: true`)
6. `contraction`      — contractions (if `no_contractions: true`)

`gate_mode` in `tailor/paths.py`:
- `warn`  — log and continue (default)
- `raise` — raise `GateFailureError`
- `skip`  — abandon and return None

## Anchor packs

`people/{name}/anchor-packs.yaml` stores pre-approved bullets per role family.
Template tier selects from these before calling the LLM, reducing prompt size and cost.
Falls back to `profile.yaml` work_history bullets if the file or role family is missing.
