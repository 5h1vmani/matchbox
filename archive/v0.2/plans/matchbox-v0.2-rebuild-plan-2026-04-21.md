# Matchbox v0.2 — Rebuild Plan

**Date:** 2026-04-21
**Status:** proposal
**Supersedes:** `refactor-plan-2026-04-21-INCREMENTAL-SUPERSEDED.md`
**Source documents:**
- `matchbox/docs/cost-optimization.md`
- `matchbox/docs/blind-spots.md`
- The marathon plan: `marathon-plan-2026-04-21.md`

## Why rebuild, not refactor

After running v0.1 for ~10 days and spending $50-150 of LLM budget on one day's work, three facts are clear:

1. **The Atma + Matchbox split costs on every tailor run.** Each agent reads 10-14 files from `atma/` and `matchbox/` independently. 22 isolated contexts × 30K tokens of shared reads = ~660K redundant tokens per batch.
2. **Mechanical work pays LLM prices.** ~80% of the cost of a tailor batch was template substitution, base64 font embedding, HTML emission, Chrome render, and regex grep — all tasks Python does for free.
3. **We're optimizing a process we can't measure.** Zero outcome data after submitting 20+ applications. Every optimization is guessing.

The incremental refactor plan fixes these one at a time while preserving v0.1's shape. But v0.1's shape IS part of the problem. The two-layer Atma+Matchbox design adds friction on every operation and makes open-sourcing clumsy (contributors have to clone and understand two systems).

v0.2 rebuilds around a single **M-silicon-style unified memory model**: one repo, one data layer, one memory layout, specialized Python pipelines that share data directly without serialization boundaries. LLM calls only where judgment is irreducible. Everything else is deterministic code.

The rebuild is 60-80 hours of focused work. It pays back after 3-5 tailor batches. And it produces something open-sourceable.

---

## Design principles (the M-silicon analogy)

Apple M-silicon wins on:
- **Unified memory.** CPU, GPU, Neural Engine share RAM. No data copies.
- **Specialized compute.** NE for ML, CPU for branchy code, GPU for parallel. The right processor for each task.
- **Zero-copy handoffs.** Data written by one unit is immediately readable by another.
- **Efficiency-first.** Every joule matters; no thermal slack.

Translated to Matchbox v0.2:

### 1. Unified memory
One SQLite database is the single source of truth for pipeline state. One directory per person holds everything about them. No "atma writes markdown, matchbox reads markdown, tailor re-serializes to HTML" churn. Components share Python dataclasses directly.

### 2. Specialized pipelines
- **Fast path (Python, free):** discovery filter, dedup, template substitution, rendering, quality gates, DB writes, outcome analytics.
- **Slow path (LLM, expensive):** bullet reformulation, summary prose, cover letter arc, red-flag judgment, keyword extraction when the JD is opaque.

These are explicit paths in code, not accidental coexistence.

### 3. Zero-copy handoffs
Discovery writes a `Job` row. Scoring reads the same row, writes back scores. Tailoring reads the scored row + a `Person` object, writes a content dict to a new `Application` row. No intermediate JSON files for "phase 2 → phase 3" handoffs. Files on disk only where crossing process boundaries (e.g., rendered PDFs).

### 4. Efficiency-first
Every LLM call has a declared budget and a declared output schema. Anything that runs at LLM pricing but doesn't need reasoning is a bug. Every batch tracks unit cost in real time and aborts if running hot.

### 5. Tight integration
Single `pip install matchbox` in one repo. Contributors clone once, run once, test once. No cross-repo version coordination. No "read Atma docs AND Matchbox docs" onboarding.

---

## What v0.2 looks like (target architecture)

```
Pinaka_speckit/                        # outer repo; atma stays here, unchanged
├── atma/                              # STANDALONE identity layer. Not part of Matchbox v0.2.
│                                      # Matchbox v0.2 copies facts from this ONCE during migration,
│                                      # then never reads atma/ again.
├── .claude/commands/                  # stays at Pinaka_speckit root; Phase 4 rewrites to CLI pointers
│
└── matchbox/                          # ← THE v0.2 REPO (gets pushed to its own GitHub repo)
    ├── README.md                      # "Matchbox v0.2 ..."; version label lives HERE, not in folder names
    ├── LICENSE                        # MIT
    ├── pyproject.toml                 # uv-managed; project name "matchbox"
    ├── .gitignore                     # archive/, people/*/db.sqlite, people/*/output/, etc
    ├── CONTRIBUTING.md                # written in Phase 5
    ├── .github/
    │   └── workflows/
    │       └── ci.yml                 # lint (ruff) + test (pytest) + render-smoke (typst)
    │
    ├── archive/                       # GITIGNORED. Local-only reference to v0.1.
    │   └── v0.1/                      # everything that was in matchbox/ before the rebuild
    │       ├── docs/
    │       ├── plans/
    │       ├── shared/
    │       ├── workflows/
    │       ├── ui/
    │       ├── people/
    │       ├── profiles.yml
    │       └── ...
    │
    ├── src/                           # src-layout: avoids package-vs-repo name collision
    │   └── matchbox/                  # Python package: `import matchbox.core.db` etc
    │       ├── __init__.py
    │       ├── core/
    │       │   ├── db.py              # SQLite SSOT; the one file with SQL
    │       │   ├── schema.py          # Pydantic models: Job, Application, Person, Response, ScanRun
    │       │   ├── person.py          # Person loader — reads people/{name}/*
    │       │   └── exceptions.py
    │       ├── discovery/
    │       │   ├── scan_daily.py
    │       │   ├── scan_funding.py
    │       │   ├── ats_probe.py       # Greenhouse/Ashby/Lever API clients
    │       │   └── sources.py
    │       ├── scoring/
    │       │   ├── rubric.py
    │       │   ├── tier_router.py     # bespoke | template | canonical | skip
    │       │   └── exclusions.py
    │       ├── tailor/
    │       │   ├── content.py         # LLM call: (person, job) → content dict
    │       │   ├── render.py          # Python + Typst: (content, template) → PDF
    │       │   ├── gates.py           # Python: all quality gates
    │       │   ├── anchor_packs.py    # tag-based bullet selection
    │       │   └── paths.py           # bespoke/template/canonical dispatch
    │       ├── outcome/
    │       │   ├── response.py
    │       │   ├── followup.py
    │       │   └── analytics.py
    │       ├── ui/
    │       │   └── ui.py              # Streamlit, for now
    │       ├── cli.py                 # `matchbox scan`, `matchbox tailor`, etc
    │       └── ingest.py              # appends to person's log.md (only Matchbox → atma/log write)
    │
    ├── shared/                        # Matchbox's own assets (not person-specific)
    │   ├── rubric.yaml                # scoring schema
    │   ├── voice-rules.yaml           # merged from ai-detection-guide + voice defaults
    │   ├── templates/
    │   │   ├── cv-canonical.typ       # Typst source (one file, geo-aware via parameter)
    │   │   └── cover-canonical.typ
    │   └── fonts/
    │       └── AtkinsonHyperlegible/
    │
    ├── people/                        # gitignored EXCEPT for maybe a demo/ added post-validation
    │   └── shiva/                     # (local only initially)
    │       ├── profile.yaml           # identity + targets + work + skills + projects + tiers + exclusions + scoring + role_family_preference + compensation + constraints
    │       ├── voice.yaml             # voice rules + examples + person-specific overrides
    │       ├── stories.md             # STAR+R narratives for cover letters + interviews
    │       ├── cv-canonical-uk.pdf    # pre-rendered for tier-3/4 UK apps
    │       ├── cv-canonical-india.pdf
    │       ├── cv-canonical-relocate.pdf
    │       ├── cover-canonical-uk.pdf
    │       ├── cover-canonical-india.pdf
    │       ├── cover-canonical-relocate.pdf
    │       ├── db.sqlite              # pipeline state
    │       ├── runs/                  # scan run artefacts (auto-created; gitignored)
    │       ├── reports/               # per-role evaluation reports (auto-created; gitignored)
    │       ├── output/                # tailored CVs + covers per job (auto-created; gitignored)
    │       └── log.md                 # activity log (written via ingest protocol only)
    │
    ├── docs/                          # all project documentation
    │   ├── README.md                  # entry point; mentions "v0.2"
    │   ├── architecture.md            # one-pager on M-silicon design
    │   ├── setup.md
    │   ├── operator-runbook.md
    │   ├── cost-optimization.md       # preserved from v0.1 analysis
    │   ├── blind-spots.md             # preserved from v0.1 analysis
    │   └── workflows/                 # human-readable procedure docs (for understanding, not execution)
    │       ├── scan.md
    │       ├── tailor.md
    │       ├── apply.md
    │       └── interview-prep.md
    │
    ├── plans/                         # THIS folder; consolidated
    │   ├── matchbox-v0.2-rebuild-plan-2026-04-21.md          ← you are here
    │   ├── marathon-plan-2026-04-21.md                       (v0.1 strategic plan; historical)
    │   ├── refactor-plan-2026-04-21-INCREMENTAL-SUPERSEDED.md (the path NOT taken)
    │   └── v0.2-drafts/
    │       ├── cv-canonical-draft.md
    │       └── cover-canonical-draft.md
    │
    └── tests/
        ├── test_schema.py
        ├── test_tier_router.py
        ├── test_render.py
        ├── test_gates.py
        ├── test_person.py
        └── fixtures/
            └── sample_job.json
```

---

## Person model: 3 files, not 12

The single biggest data-layer win. Per person:

### `profile.yaml` — everything structured
One file. All facts, all targets, all filters, all dream tiers, all exclusions, all compensation, all constraints. Structured. Queryable. No-fabrication source.

```yaml
candidate:
  full_name: Shiva Padakanti
  email: ...
  phone: ...
  location: Hyderabad, India
  languages: [...]
  linkedin: ...
  github: ...

targets:
  primary_roles: [...]
  archetypes: [...]
  dream_tiers:
    tier_1_dream: [...]
    tier_2_target: [...]
    tier_3_watchlist: [...]

filters:
  title_positive: [...]
  title_negative: [...]
  keywords: [...]
  exclusions:
    defense: { global_default: exclude, overrides: { india: include } }
    crypto: { global_default: exclude }
    # ...

compensation:
  india: { target: "₹60-85 LPA + equity", minimum: "₹35 LPA" }
  # ...

constraints:
  visa_status: ...
  remote_preference: ...
  # ...

scoring:
  cv_match_weight: 0.25
  company_mission_fit_weight: 0.15
  # ...

work_history:
  - company: NTT DATA London
    role: Senior Associate, Finance Transformation
    dates: 2022-06 to 2024-06          # ← one source of truth for the 2-year fact
    tenure_years: 2
    location: London, UK
    tags: [enterprise, post-merger, sap-analytics, europe, training]
    bullets:
      - text: "Led the migration of 30 entities across Europe from Excel-based reporting to SAP Analytics Cloud."
        tags: [platform-migration, scale, enterprise]
        voice_verified: true
        facts_verified: true
      - text: "..."
        # ...
  - company: Vidhar
    # ...

skills:
  - name: "AWS Lambda"
    category: backend
    evidence: [pinaka, matchbox, vasapitta]
  # ...

projects:
  - name: Pinaka
    status: private-repo
    dates: 2025-08 to present
    tags: [edtech, aws-serverless, react, typescript, load-tested]
    load_test_ccu: 250000
    # ...

role_family_preference:
  1: solutions_architect_startups
  2: solutions_architect_general
  # ...
```

### `voice.yaml` — rules + examples
```yaml
hard_rules:
  no_em_dashes: true
  no_contractions: true
  banned_words: [leverage, synergy, passionate about, spearhead, orchestrate, ...]
  banned_openers: ["I am writing", "I am excited", "As a [role] with [years]"]

required_signals:
  min_named_entities_per_150_words: 3
  min_numbers_per_150_words: 2
  min_authenticity_signals: 3

voice_variants:
  costly_signal_patterns:
    - "Five months ago I had never shipped production code of my own."
    - "My backend stack is Python on AWS Lambda, not Go or Rust."
  opener_patterns:
    - "In October 2025 I fired the development team three weeks in."
    - "The target user of {company} is the person I was two years ago."
```

### `stories.md` — prose narratives
For cover letters, interview STAR+R prep, and long-form outputs.
Merges today's `narrative.md` + `story-bank.md`.
~10-15 curated stories, each tagged by when to deploy.

### Plus the canonical CV + cover (2 files, version-controlled)
- `cv-canonical.typ` — handwritten by the person, reviewed, voice-verified
- `cover-canonical.typ` — handwritten, generic-enough for tier-3/4 applications

**Total person-specific files: 5.** Down from today's 12. Every agent read is ~60% cheaper forever.

---

## What we keep from v0.1

Things that worked. Don't throw them out.

| v0.1 concept | Keep in v0.2 because |
|---|---|
| SQLite as SSOT for pipeline state | Proven, atomic, queryable, zero-dependency |
| 6-dimension scoring rubric | Works; the refactor simplifies internals but keeps the schema |
| Sector exclusions with geo overrides | Compact, correct, reused everywhere |
| Dream tiers (tier_1_dream, tier_2_target, tier_3_watchlist, tier_4_exploratory) | Drive tier router directly |
| Funded-news scan flow | Efficient; Phase 1 pattern carries forward |
| ATS API probe approach (Greenhouse, Ashby, Lever slugs) | Free and accurate for ~40-50% of companies |
| Voice rules + banned-word grep gate | Works deterministically |
| Multi-app hygiene rule | Correct and essential |
| Role family preference within-company sort | Addresses a real UX problem |
| Streamlit UI (for now) | Functional; migrate only when open-sourcing |
| Soft cooling filter (hide not block) | Right behavior pattern |
| Budget caps in config | Wire them into real enforcement |

---

## What gets killed or radically reshaped

| v0.1 thing | What v0.2 does |
|---|---|
| **`atma/` directory** | Collapses into `matchbox/people/{name}/`. Identity data IS Matchbox's native memory. |
| **12 identity files** | 3 files (`profile.yaml`, `voice.yaml`, `stories.md`) + 2 canonical artefacts |
| **`atma/shared/` + `matchbox/shared/`** | One `matchbox/shared/` directory |
| **routing.md + index.md** | Python modules declare what they read; no meta-file needed |
| **HTML template + base64 fonts + Chrome** | Typst templates. Package-managed fonts. Deterministic pagination. No Chrome. |
| **22-agent tailor batch** | Single Python orchestrator loops through jobs; one LLM call per job, prompt-cached shared prefix |
| **Content = HTML output** | Content = JSON dict; Python renders |
| **LLM-interpreted quality gates** | Python functions; deterministic |
| **Slash commands as primary interface** | CLI (`matchbox scan`, `matchbox tailor`, `matchbox apply`). Slash commands become 4-line pointers to CLI. |
| **Flat per-app cost (~$1-2 each)** | Tier-based: $10-20 for tier-1, $1-2 for tier-2, $0.05 for tier-3 canonical |
| **Workflow `.md` files as procedure specs for agents** | Python functions with docstrings. Markdown workflows become human-readable documentation only. |
| **Report files as loose markdown** | Stored in DB as evaluation rows; rendered to markdown on demand (not the persistence layer) |
| **JSON checkpoint files between scan phases** | In-memory handoffs between Python modules. Only persist at phase boundaries that cross process boundaries. |

---

## Migration plan (6 phases)

Total effort: **60-80 hours**. Distributable across 2-3 weeks.

### Phase 1 — Foundation (8-10 hours)

**Goal:** scaffold the new repo structure and core data layer. Nothing user-facing changes yet; v0.1 keeps running.

1.1. Create `pyproject.toml` and Python module skeleton.
1.2. Build `matchbox/core/schema.py` with Pydantic models (Job, Application, Person, Response, ScanRun).
1.3. Build `matchbox/core/db.py` (port from current `matchbox/shared/db.py`; add Pydantic-based row conversion).
1.4. Build `matchbox/core/person.py`: loader that reads `profile.yaml`, `voice.yaml`, `stories.md` into Person object.
1.5. Write `tests/test_schema.py` and `tests/test_person.py`. 10+ cases. Pytest.
1.6. One-time migration script: `migrate_atma_to_profile.py` converts current 12-file Atma to 3-file profile/voice/stories + facts verification.

**Success criterion:** `from matchbox.core import Person; p = Person.load("shiva")` returns a fully-populated object with no fact errors. All tests green.

**Key risk:** the migration script must not drop any fact. Manual diff against v0.1 mandatory.

### Phase 2 — Pipeline modules (12-15 hours)

**Goal:** port discovery, scoring, and outcome modules to the new structure.

2.1. Build `matchbox/discovery/` (scan_daily, scan_funding, ats_probe, sources). Port from v0.1 workflows; convert to Python functions that return dataclass lists.
2.2. Build `matchbox/scoring/` (rubric, tier_router, exclusions). Keep 6-dim rubric for now; refactor to use Person object and return scored rows directly to DB.
2.3. Build `matchbox/outcome/` (response logger, follow-up reminder, analytics).
2.4. Wire DB migrations: add `response_date`, `response_type`, `response_note`, `tailor_tier`, `tailor_cost_usd` columns.
2.5. Tests for each module.

**Success criterion:** `matchbox scan --profile shiva --mode funded_recent` runs end-to-end, produces new jobs in DB with correct scores. Equivalent to v0.1's scan pipeline but all Python, no markdown-workflow-agent loops.

### Phase 3 — Tailor rebuild (15-20 hours)

**Goal:** the big win. Replace 22-agent fan-out with content-as-JSON + Python render + tier routing.

3.1. Write canonical CV and canonical cover in Typst. Manually crafted by Shiva. Voice-verified.
3.2. Build `matchbox/tailor/render.py`: Typst template + content dict → PDF. Deterministic.
3.3. Build `matchbox/tailor/gates.py`: 4 quality gates as Python functions.
3.4. Build `matchbox/tailor/content.py`: ONE Sonnet call per job, structured JSON schema output.
3.5. Build `matchbox/tailor/anchor_packs.py`: tag-based bullet selection from `profile.yaml:work_history.bullets`.
3.6. Build `matchbox/tailor/paths.py`: bespoke, template, canonical paths.
3.7. Build `matchbox/tailor/tier_router.py`: classifies job, routes to the right path.
3.8. Integration tests: run one bespoke + one template + one canonical tailor end-to-end.

**Success criterion:** tailor a test batch of 5 jobs (1 bespoke + 2 template + 2 canonical) end-to-end in < 10 min, total cost < $3. All outputs pass gates.

### Phase 4 — CLI + UI (5-7 hours)

4.1. Build `matchbox/cli.py` with subcommands: `scan`, `tailor`, `apply`, `score-job`, `log-response`, `analytics`.
4.2. Port Streamlit UI to import the new Python modules instead of reading markdown.
4.3. Add the response-logging form and follow-up reminder panel.
4.4. Update slash commands in `.claude/commands/*.md` to 4-line pointers calling CLI.

**Success criterion:** both `matchbox scan --profile shiva` and `/scan-jobs --profile shiva` produce identical results. UI shows outcome-logging UI.

### Phase 5 — Documentation + open-source readiness (6-8 hours)

5.1. Rewrite `docs/README.md` for v0.2 (one-repo, `pip install matchbox`).
5.2. Rewrite `docs/architecture.md` reflecting the M-silicon model.
5.3. Rewrite `docs/setup.md` for v0.2 workflow.
5.4. Rewrite `docs/operator-runbook.md` for the tier-based workflow.
5.5. Produce `CONTRIBUTING.md`, `LICENSE`, `.env.example`.
5.6. Publish to GitHub (private or public per user's call).

**Success criterion:** a stranger clones the repo, runs `pip install -e .`, follows setup.md, scans + tailors one job successfully.

### Phase 6 — Cutover + deprecation (4-6 hours)

6.1. Run v0.2 and v0.1 in parallel for one week. Compare outputs on the same queue.
6.2. Once v0.2 produces equal-or-better results: archive `atma/` and `.claude/commands/` to a git branch.
6.3. Delete `atma/` from main branch. `.claude/commands/` stays as 4-line pointers to CLI.
6.4. Update cost-optimization.md and blind-spots.md with actual v0.2 numbers.

**Success criterion:** v0.1 can be fully retired. Everything runs on v0.2.

---

## The three files in v0.2 Person — why this is the right number

After rebuild, a person is described by exactly:

1. **`profile.yaml`** — structured facts. Queryable. Machine-readable. Source of truth for every name, date, number, tenure. Eliminates the "NTT DATA 2 vs 4 years" class of error permanently.

2. **`voice.yaml`** — rules + examples. Machine-enforceable (grep). Structured overrides allow per-person voice customization without forking the codebase.

3. **`stories.md`** — prose. Intentionally unstructured. For cover letters, interview prep, narrative contexts where structure kills flow. Tagged at the top for retrieval.

Plus 2 canonical artefacts (`cv-canonical.typ` + `cover-canonical.typ`) that the person OWNS and edits. These aren't "data about the person"; they're the person's curated output. Different role.

Why not 4 or 2?
- **Not 4:** the next candidate (after removing Atma abstraction) would be splitting `profile.yaml` into `facts.yaml` + `targets.yaml`. But they're read together 99% of the time. One file.
- **Not 2:** merging stories into yaml destroys prose flow. Structured + unstructured can't live in one format.

---

## Open-source considerations

v0.2 makes Matchbox genuinely ship-able:

**Before (v0.1):**
- Two repos: Matchbox + Atma (implicit)
- Person data scattered across 12 files in nested directories
- Markdown-workflow-driven agent loops (hard to contribute to)
- No CLI; requires Claude Code
- No pytest; no CI
- Mixed languages: YAML configs + markdown workflows + Python scripts + HTML templates + base64 fonts

**After (v0.2):**
- One repo
- `pip install matchbox`
- Real Python package, importable
- Proper CLI
- Pytest suite
- Typst templates (one language, actually designed for typesetting)
- Workflows are Python functions with docstrings; markdown docs describe behaviour
- Contributors understand the shape in 10 minutes

**Licensing:** **MIT** (confirmed with user 2026-04-21). Fonts (Atkinson Hyperlegible) are SIL OFL, bundleable. Shared assets (rubric, voice rules) under MIT. Person-specific `people/*/` directories are gitignored by default; users opt-in to commit their own profile.

**Demo profile:** deferred until after v0.2 is validated with Shiva + interns. Not part of initial public release.

---

## Success metrics (what we're measuring)

Compared to v0.1:

| Metric | v0.1 today | v0.2 target | Why |
|---|---:|---:|---|
| Cost per 20-job tailor batch | $25-70 | **$3-8** | content-as-JSON + tier routing + prompt caching |
| Wall-clock per 20-job batch | 80 min | **30 min** | single Python orchestrator, no 22-agent fan-out |
| Person files | 12 | **5** (3 core + 2 canonical artefacts) | Atma collapse |
| Shared files per tailor read | 10-14 | **3** | profile + voice + stories |
| Factual-error propagation (e.g., "NTT DATA 4 years") | possible (happened today) | **blocked at load time** | single YAML SSOT |
| Test coverage | 0% | **60%+** | pytest from day 1 |
| Time to onboard a new contributor | ~4 hours | **30 min** | one repo, pip install, run |
| Outcome data (responses logged) | 0 | 20+ after 30 days | UI + follow-up reminder |
| Matchbox installable by non-Claude-Code users | no | **yes** | CLI entry point |

---

## What this plan does NOT attempt

- **Migrate off Streamlit.** Keep for now; port to FastAPI+HTMX post-open-source only if real users complain.
- **Build the recruiter CRM.** Defer until there are recruiter relationships to track.
- **Warm-intro tracking.** Requires workflow design, not code.
- **Re-scoring old rows after rubric changes.** One-shot migration script; not a system capability.
- **Interview-prep LLM tooling.** Scaffold the workflow doc; full implementation comes after v0.2 is stable.
- **Multiple-person multi-tenant UI.** One user per Streamlit instance; profile-switching is fine.

These are all worth future work. Not in this rebuild.

---

## Key risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Migration drops facts (like the NTT DATA tenure) | High | Phase 1.6 migration script produces a diff report. Manual review mandatory before accepting. |
| Typst migration has a learning curve and breaks CV styling | Medium | Phase 3.1 has a one-week buffer. If Typst is too fragile, fall back to HTML+Chrome with cleaner Python wrappers. |
| v0.2 produces lower-quality output than v0.1 (the factor we can't predict) | Medium | Phase 6 runs both in parallel for one week on the same queue; only cut over if outputs match quality. |
| 60-80 hours drags to 120+ | Medium-high | Phase cutoffs are hard checkpoints. If Phase 2 runs over by 50%, STOP and reassess scope. |
| We over-engineer the schema in Phase 1 | Medium | Pydantic schema reviewed against 10+ real tailor outputs before Phase 2 starts. |
| Open-sourcing early exposes half-baked code | Low | Ship only after Phase 5 complete + 1 week of v0.2 running in production. |
| User's canonical CV is worse than what the tailor produces | Low | Human review; iterate. Shiva writes; Claude critiques. |

---

## Decision points for the user

Before starting Phase 1, confirm:

1. **Rebuild vs refactor?** If you'd prefer the incremental path, we use `refactor-plan-2026-04-21-INCREMENTAL-SUPERSEDED.md` (preserved in this folder). If rebuild, proceed with this doc.
2. **Typst or keep HTML+Chrome?** Typst is better but has learning curve. Decide before Phase 3.
3. **Open-source timing?** Public right after Phase 5, or wait 3-6 months for field use?
4. **v0.2 development branch?** Develop on `v0.2-dev` branch; merge to main after Phase 6?
5. **Canonical CV/cover authorship?** You write these yourself in Phase 3.1; Claude provides critique. Acceptable?

---

## Priority order for execution (within the plan)

Ranked by **stop-the-bleeding**:

1. **Phase 2.4 (DB response columns) + Phase 4 (CLI skeleton just for `log-response`)** — 2 hours. Start capturing outcome data IMMEDIATELY, even before v0.2 is done. This is the blindest spot.
2. **Phase 1.6 (migration script) + manual migration to `profile.yaml`** — 6 hours. Eliminates fact drift forever.
3. **Phase 3.1 (canonical CV + cover)** — 4 hours of user time. Instantly saves 80% of tailor cost on next batch.
4. **Phase 3.2-3.7 (tailor rebuild)** — 12-15 hours. The core cost and quality win.
5. **Phase 2.3 (outcome tracking) + Phase 4 (UI outcome form)** — 3 hours. Closes the feedback loop.
6. **Phases 1, 2, 3.8 (the rest of foundations + discovery + tailor tests)** — 15 hours. Stabilize.
7. **Phases 5 + 6 (docs + cutover)** — 10 hours. Ship.

---

## Review cadence

- After each Phase: compare actual hours to estimate. If overage > 50%, stop and replan.
- After Phase 3: compare v0.2 tailor output quality to v0.1 on a 5-job test set. User signs off.
- After Phase 6: compare v0.2 running-cost to v0.1 over 2 weeks of real use.
- **Review by:** 2026-07-21 (3 months). Either v0.2 is shipping or we reassess.

---

# CONFIRMED DECISIONS — 2026-04-21

User has locked in the following during the planning conversation. Any future-me picking this plan up after context compaction should treat these as settled, not open questions.

## Decision 1: Full rebuild (not incremental refactor)

v0.2 is a ground-up rebuild. The incremental refactor plan is preserved at `refactor-plan-2026-04-21-INCREMENTAL-SUPERSEDED.md` for reference only. Do not use it.

## Decision 2: Archive v0.1 inside `matchbox/archive/v0.1/`, gitignored

Scope of archive: **only `Pinaka_speckit/matchbox/` contents**. NOT atma. NOT `.claude/commands/`.

- `atma/` stays at `Pinaka_speckit/atma/` untouched. It is a standalone identity layer that persists beyond Matchbox. Matchbox v0.2 copies facts from atma into `people/shiva/*` ONCE during Phase 1 migration, then severs the dependency; Matchbox never reads `atma/` again.
- `.claude/commands/` stays where it is. Slash commands pointing at archived workflows will break temporarily; Phase 4 rewrites them as 4-line pointers to the v0.2 CLI.

**Archive procedure:**

```bash
cd /Users/yantram/Desktop/Pinaka_speckit/matchbox
# Stage everything currently in matchbox/ to move into archive/v0.1/
mkdir -p archive/v0.1
# Move all top-level items (docs, plans, shared, workflows, ui, people, profiles.yml, etc.)
# EXCEPT the archive/ dir itself
for item in *; do
  if [ "$item" != "archive" ]; then
    git mv "$item" "archive/v0.1/$item"
  fi
done
# Add .gitignore at matchbox/ root
echo "archive/" > .gitignore
echo "people/*/db.sqlite" >> .gitignore
echo "people/*/output/" >> .gitignore
echo "people/*/runs/" >> .gitignore
echo "people/*/reports/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo ".env" >> .gitignore
echo ".venv/" >> .gitignore
git add .gitignore
git commit -m "chore: archive v0.1 before v0.2 rebuild"
```

After archive: `matchbox/` root is empty except for `archive/` (gitignored) and `.gitignore`. v0.2 starts from a clean slate at `matchbox/` root. Archive directory stays local, never pushed to GitHub.

**Note on folder naming:** no `v0.2` suffix anywhere in directory names. The version label lives only in `README.md`, `pyproject.toml` version field, and docs. Directory structure under `matchbox/` is the current version by convention.

## Decision 3: Rendering format = Typst

User said "whatever works, effective, cheaper, clean." Typst wins on all three vs HTML+Chrome and vs LaTeX. Reasoning:
- **Effective:** designed for typesetting from structured data; deterministic pagination natively
- **Cheaper:** no Chrome process to manage; no base64 fonts in LLM output stream; ~$0 per render vs today's Chrome-render cost
- **Clean:** package-managed fonts; one language (Typst) for all document artefacts; ~100 lines of template replaces ~3000 lines of HTML+CSS

Commit to Typst in Phase 3. Fall-back to HTML+Chrome is in the risk table but shouldn't be needed.

## Decision 3a: Tier-based rendering strategy (NEW — user insight)

Not every tailored artefact needs to be rendered at job-submission time. The render strategy asymmetry:

| Tier | Render strategy | Cost per app | Why |
|---|---|---:|---|
| **Tier 3 / Tier 4 canonical** | **Pre-rendered, static** — three PDF variants per document type (UK, India, Relocate), generated ONCE, stored on disk, Python picks + copies the correct variant per application | ~$0 | Content is identical across all tier-3 apps. Rendering the same content 50 times is waste. |
| **Tier 2 template** | **Render at tailor time** from parameterized Typst template. One Sonnet call fills an anchor-pack selection; Python renders the Typst with content + geo-correct footer baked in per application | ~$0.05-0.30 | Mild per-company variation (company name, role family pack). Render once per app. |
| **Tier 1 bespoke** | **Render at tailor time** from the SAME parameterized Typst template. Full-custom Sonnet-generated content substituted; geo-correct footer chosen via parameter | ~$5-15 | Fully bespoke content per app. The render pipeline is the same shape as tier-2, but the content generation step is heavier. |

**Artefacts produced in Phase 3:**

- `people/shiva/cv-canonical.typ` — ONE source file, geo-aware via parameter
- `people/shiva/cover-canonical.typ` — ONE source file, geo-aware via parameter
- Pre-rendered outputs (generated by Phase 3.1 manually, then whenever canonical source edits):
  - `people/shiva/cv-canonical-uk.pdf`
  - `people/shiva/cv-canonical-india.pdf`
  - `people/shiva/cv-canonical-relocate.pdf`
  - `people/shiva/cover-canonical-uk.pdf`
  - `people/shiva/cover-canonical-india.pdf`
  - `people/shiva/cover-canonical-relocate.pdf`

**Geo footer rules:**
- `uk` variant: "Six years of UK work history (Tier 4 student 2018-2020, Tier 2 work 2020-2024)."
- `india` variant: no footer line (Hyderabad-based, local).
- `relocate` variant: "Willing to relocate for the right role."

**Regeneration trigger:** whenever `cv-canonical.typ` or `cover-canonical.typ` source is edited, Python CLI command `matchbox rebuild-canonicals --profile shiva` re-renders all 6 static PDFs in one pass. Fast (~3 seconds total via Typst). Developers run this after any source edit.

**Submission logic (tier 3/4):**
```python
def tailor_canonical(job: Job, person: Person) -> Application:
    geo = infer_geo(job.country)     # returns "uk" | "india" | "relocate"
    cv_src  = f"people/{person.name}/cv-canonical-{geo}.pdf"
    cov_src = f"people/{person.name}/cover-canonical-{geo}.pdf"
    cv_dst  = out_path(job, "cv")
    cov_dst = out_path(job, "cover")
    shutil.copy(cv_src, cv_dst)
    shutil.copy(cov_src, cov_dst)
    return Application(cv_path=cv_dst, cover_path=cov_dst, tier="canonical", cost_usd=0)
```

**Submission logic (tier 1/2):**
```python
def tailor_bespoke_or_template(job: Job, person: Person, tier: str) -> Application:
    geo = infer_geo(job.country)
    content = generate_content(job, person, tier, geo)   # Sonnet call (JSON schema output)
    cv_typst = render_typst(template="cv-canonical.typ", content=content, geo=geo)
    cv_pdf   = typst_to_pdf(cv_typst)
    # ...similar for cover
    return Application(cv_path=cv_pdf, cover_path=cov_pdf, tier=tier, cost_usd=...)
```

**Key insight from user:** don't re-render the same PDF 50 times. Pre-render once, copy at submission time. LLM cost on tier-3/4: zero. Disk cost: 6 PDFs (~60KB each = ~360KB total).

## Decision 4: Open source timing — **4-6 weeks of self + intern testing, then public release**

Options considered:
- Day 1 after Phase 5 → too raw; contributors see issues
- After 3-6 months of field use → momentum dies
- Hybrid (picked) → 4-6 weeks private dogfooding

**Recommended sequence:**
1. **Week 0 (end of Phase 5):** private GitHub repo. Shiva + 2-3 interns get access.
2. **Weeks 1-4:** Shiva runs full cycles; interns run cycles with their own profiles. Every bug they hit goes into issues. Every confused onboarding step goes into docs.
3. **Week 4 checkpoint:** review. If no critical issues, proceed. If critical issues, fix and add 2 more weeks.
4. **Week 5-6:** polish docs, add `CONTRIBUTING.md`, `LICENSE` (MIT), demo profile (`people/demo/`), and a short screencast/README GIF. Write an announcement blog post.
5. **Week 6-8:** flip repo to public. Post on HN, Twitter/X, relevant Discords (Anthropic community, AI-search, YC forums). Track engagement.

**Why this timing matters:**
- 3 users exposes 80% of the edge cases a solo user will not hit
- 4-6 weeks is enough to fix serious bugs but not long enough that the project drifts
- Releasing too early = contributors see janky code, bounce, tell their friends
- Releasing too late = you build features nobody asked for, lose first-mover value
- Personal upside: builders at Lovable/Cursor/Anthropic/Factory will notice a genuinely good open-source tool built with their stack. This is career leverage beyond the job applications themselves.

**Licensing:** MIT. Fonts are SIL OFL (bundleable). Shared assets (rubric, voice rules) under MIT. Person-specific `people/*/` directories are gitignored by default; users opt-in to commit their own profile.

**Demo profile:** Phase 5 includes a fictional `people/demo/` candidate so anyone can run the full pipeline without writing their own profile first.

## Decision 5: Testing cohort — self + 2-3 interns first

Confirmed. The 2-3 interns already working with Shiva become the initial user base during weeks 1-4. Each gets their own `people/{name}/` directory, private to them via `.gitignore`.

## Decision 6: Fresh GitHub repo

No v0.1 code pushed. Repo is clean-history v0.2 at first commit. Keeps the public project free of the evolutionary cruft.

## Decision 7: Canonical CV + cover drafted now

Drafts saved at:
- `matchbox/plans/v0.2-drafts/cv-canonical-draft.md`
- `matchbox/plans/v0.2-drafts/cover-canonical-draft.md`

Shiva reviews and edits these. Final versions convert to Typst during Phase 3. These are the 80% fallback artefacts that tier-3 and tier-4 applications use verbatim (pre-rendered PDF, picked by geo).

**Confirmed content choices:**
- Projects included: Pinaka, Matchbox, Bodhi, Kubera, Usepaso (5 total).
- Projects excluded from canonical: Vasapitta (include in bespoke CVs where cost-constrained ops is valued by the JD; not in canonical).
- Geo line: NOT in the canonical source directly. Lives in the 3 pre-rendered variants (`cv-canonical-uk.pdf` with UK auth line, `cv-canonical-india.pdf` with no footer, `cv-canonical-relocate.pdf` with relocation line). Render-time parameter, not static source content.

## Decision 8: Git and tooling stack (user delegated to recommendation)

- **Branch strategy**: `main` only until there's a team. Feature branches when contributors arrive. No `v0.2-dev` branch — the whole repo IS v0.2 work.
- **Commit convention**: Conventional Commits. Types used: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.
- **Python version**: 3.12+ (match user's current environment).
- **Package manager**: `uv` (fast, modern, lockfile-based). `pip` fallback works because `uv` uses `pyproject.toml`.
- **Testing framework**: `pytest` + `pytest-asyncio` for any LLM-mock scenarios.
- **Code style**: `ruff` for linting AND formatting. One tool. Replaces Black + isort + flake8.
- **Type checking**: `mypy --strict` on new code. CI-enforced.
- **CI**: GitHub Actions, single workflow file (`.github/workflows/ci.yml`): lint + test + render-smoke. Free tier.
- **Dependency management**: `pyproject.toml` with `[project]` + `[project.optional-dependencies]` blocks. Dev deps under `[project.optional-dependencies.dev]`.
- **Python packaging layout**: `src/` layout (`src/matchbox/...`) to avoid package-vs-repo name collision and accidental "import from cwd" bugs.

---

# ARCHIVE STRATEGY (precondition for Phase 1)

Before any v0.2 code is written:

1. **Create `_archive/v0.1/`** directory at repo root.
2. **Git-move (not copy)** all existing directories into it:
   - `atma/` → `_archive/v0.1/atma/`
   - `matchbox/` → `_archive/v0.1/matchbox-v0.1/` (but first extract `docs/` and `plans/` to preserve analysis work — see below)
   - `.claude/commands/` → `_archive/v0.1/claude-commands/`
3. **Extract seed documents** for v0.2 from the archive before gitignoring:
   - `_archive/v0.1/matchbox-v0.1/docs/cost-optimization.md` → `docs/cost-optimization.md` (at v0.2 root)
   - `_archive/v0.1/matchbox-v0.1/docs/blind-spots.md` → `docs/blind-spots.md`
   - `_archive/v0.1/matchbox-v0.1/plans/*` → `plans/*` (this plan file itself stays with plans)
4. **Add `_archive/` to `.gitignore`**. Archive exists locally for reference but never gets pushed.
5. **Git commit** the clean slate with message: `Archive v0.1 before v0.2 rebuild`.
6. **Initialize new GitHub repo** (private) and push this first commit. Add collaborators (Shiva + interns).

After this preamble, v0.2 Phase 1 begins on a clean tree.

---

# RESTART CHECKLIST (for post-compaction me)

If you are a fresh instance of Claude reading this after context was compressed, here is everything you need to pick up:

## What has been decided
- **Rebuild, not refactor.** v0.2 is ground-up. Incremental refactor plan is SUPERSEDED.
- **Archive scope**: only `Pinaka_speckit/matchbox/` contents → `Pinaka_speckit/matchbox/archive/v0.1/` (gitignored). **atma/ stays put**, untouched, standalone. `.claude/commands/` stays put, rewritten in Phase 4.
- **Repo location on disk**: `/Users/yantram/Desktop/Pinaka_speckit/matchbox/` (same path as today; v0.1 archived inside `archive/` subdirectory). No `v0.2` in folder names.
- **License: MIT.**
- **Rendering: Typst** (one source file per document type, geo-parameterized at render time).
- **Tier 3/4 canonical strategy**: three pre-rendered PDF variants per document type (`-uk`, `-india`, `-relocate`), generated once, copied at submission time. Zero LLM, zero per-app render. Regenerated only when canonical source is edited (`matchbox rebuild-canonicals` CLI command).
- **Tier 1/2**: render per-job via Typst with parameterized content + geo footer.
- **Open source timing**: 4-6 weeks private testing with Shiva + 2-3 interns, then public release on a fresh GitHub repo.
- **3 files per person** + pre-rendered canonical PDFs:
   - `profile.yaml` (structured: identity + targets + work + skills + projects + tiers + exclusions + scoring + role_family_preference + compensation + constraints)
   - `voice.yaml` (rules + person-specific overrides + example phrasings)
   - `stories.md` (prose narratives for cover letters and interview prep)
   - `cv-canonical-{uk,india,relocate}.pdf` (pre-rendered, tier-3/4 fallback)
   - `cover-canonical-{uk,india,relocate}.pdf` (same)
- **Tooling stack**: Python 3.12+, `uv`, `pytest`, `ruff`, `mypy --strict`, GitHub Actions (single CI workflow), Conventional Commits, `main`-branch-only until team.
- **Python packaging**: `src/matchbox/` layout.
- **M-silicon architecture**: unified memory (one SQLite + one directory per person), specialized pipelines (Python for mechanical, LLM for judgment), zero-copy handoffs (Pydantic models shared across modules), efficiency-first (every LLM call has a declared budget and output schema).

## What is NOT yet done
- Archive procedure — not yet executed
- Fresh repo structure — not yet created
- Any v0.2 code — not written
- Shiva has NOT yet reviewed / edited the canonical CV and cover drafts (must happen before Phase 3 rendering)
- GitHub repo not yet initialized (Shiva pushes after implementation)
- Interns not yet onboarded (happens after Phase 5)

## What to do first when resuming
1. **Ask Shiva** whether the canonical CV and cover drafts look right. Paths:
   - `matchbox/plans/v0.2-drafts/cv-canonical-draft.md`
   - `matchbox/plans/v0.2-drafts/cover-canonical-draft.md`
   Read them, summarize what each contains, ask for edits. Do NOT implement anything before Shiva confirms these are ready or gives edits.
2. **Ask whether to proceed with archive procedure** (the bash in Decision 2 above). If yes, execute it. Verify archive/ has all v0.1 contents and matchbox/ root is empty except .gitignore + archive/.
3. **Initialize the v0.2 repo structure** per the directory diagram. Create empty files and directories matching it. `pyproject.toml`, `LICENSE` (MIT), `README.md` (placeholder "Matchbox v0.2 — WIP"), `.gitignore` (already present from archive step), `.github/workflows/ci.yml` (stub), `tests/` dir, `src/matchbox/` package skeleton with empty `__init__.py` in each subpackage.
4. **Start Phase 1**: Pydantic schema + Person loader + migration script from atma/ + first tests.
5. **git init + git commit** at each meaningful milestone using Conventional Commits style.

## What to consult before making architecture decisions
- This plan file (highest priority)
- `matchbox/docs/blind-spots.md` (meta-principles about what not to build)
- `matchbox/docs/cost-optimization.md` (specific efficiency wins inside the pipeline)
- `matchbox/archive/v0.1/shared/db.py` (the SQLite access layer from v0.1; good patterns carry forward)
- `atma/people/shiva/wiki/*` at Pinaka_speckit root (source material for building `profile.yaml`; every fact here needs to land in the new structured form. Atma is NOT archived; read it in place.)

## Critical facts locked for Shiva's identity (from v0.1 audit — DO NOT CORRUPT DURING MIGRATION)
- Full name: Shiva Padakanti
- Location: Hyderabad, India
- Languages: Telugu, Hindi, English (all native-bilingual)
- **NTT DATA London tenure: Jun 2022 to Jun 2024 = exactly 2 years** (not 4)
- **Deltabase tenure: 2019 to 2022 = approximately 3 years**
- **Combined UK tenure: approximately 6 years** (MSc + Deltabase + NTT DATA, 2018-2024)
- Isha Foundation Sadhanapada: Jun 2024 to Mar 2025 (10 months)
- Vidhar founded: August 2025
- Pinaka: load-tested to 250,000 concurrent users via K6 on 10 parallel EC2 instances. NOT live with real users. Private repository.
- Deltabase output: 42+ due diligence reports, 58-60% research time savings via AI-assisted synthesis
- NTT DATA output: 30 entities, 150+ users trained across Europe (London, Frankfurt, Munich, Prague)
- Isha output: Prana Dhanam 5,000+ meals daily, 100+ rotating volunteers across 9 departments
- UK visa history: Tier 4 student (2018-2020) + Tier 2 work (2020-2024)
- **Do not claim "four years at NTT DATA" anywhere.** This was a repeated error in v0.1 tailored outputs.

## Open questions Shiva may still need to answer
1. Photo on CV? (current draft: no photo, international technical convention)
2. Tagline under name? (current draft: none)
3. ADP experience expansion? (current draft: "Earlier Experience" one-liner)
4. Canonical CV projects: Pinaka + Matchbox + Bodhi + Kubera + Usepaso (5). Vasapitta excluded — confirmed.
5. Geo footer now parameterized: UK / India / Relocate variants, 3 pre-rendered PDFs. Confirmed.
6. Git commit style: Conventional Commits. Confirmed.
7. License: MIT. Confirmed.
8. Announcement plan (HN, X, Discord posts): draft after Phase 5 ready? (yes)

---

# MULTI-PROFILE ARCHITECTURE — 2026-04-21

User confirmed all 5 recommendations. This section documents how Matchbox handles multiple profiles (Shiva + interns + eventual OSS contributors) cleanly.

## Core principle

Every decision is either **repo-level** (generic, ships under MIT to every user) or **profile-level** (person-specific, gitignored by default). No leaky overlap. When code needs a profile-specific value, it loads from `people/{name}/`. When it needs a generic default, it loads from `shared/`. When both apply, Python merges (overrides win).

## Decision 1: Separate SQLite DB per profile

`people/{name}/db.sqlite`. One DB per person. No shared DB across profiles.

Benefits:
- Strong isolation: bugs cannot leak rows across profiles.
- OSS safety: each DB is inside `people/{name}/` which is gitignored; no one can accidentally push another user's data.
- Backup/restore is a single-file copy.
- File permissions on multi-user machines work naturally.
- Matches M-silicon per-core cache analogy — each profile gets its own memory space.

Python connects via `db_for(profile_name)` → `sqlite3.connect(f"people/{profile_name}/db.sqlite")`. Same pattern as v0.1; keep it.

## Decision 2: Voice rules layering (defaults + overrides)

Two files:
- `shared/voice-rules.yaml` — universal defaults (no em dashes, no contractions, generic banned words). MIT-licensed, ships with the repo.
- `people/{name}/voice.yaml` — per-profile overrides. Adds person-specific forbidden phrases, opener variants, required authenticity signals. Gitignored.

**Merge semantics at Person load time:**
```python
def load_voice_rules(person_name: str) -> VoiceRules:
    defaults  = yaml.safe_load(open("shared/voice-rules.yaml"))
    overrides_path = Path(f"people/{person_name}/voice.yaml")
    if overrides_path.exists():
        overrides = yaml.safe_load(overrides_path.open())
        return VoiceRules.from_merged(defaults, overrides)  # overrides win
    return VoiceRules.from_dict(defaults)
```

The Person object holds fully-resolved rules; downstream code never sees the shared-vs-override distinction. Unified memory principle.

**Lists vs maps:** for list fields (e.g., `banned_words`), overrides APPEND to defaults unless an explicit `replace: true` flag is set. For map fields, overrides REPLACE by key. Documented in `shared/voice-rules.yaml` header.

## Decision 3: Demo profile is the ONLY committed profile (post-validation)

`.gitignore`:
```
people/*
!people/demo/
!people/README.md
```

- `people/shiva/` — Shiva's personal data, never pushed.
- `people/{intern-name}/` — each intern's personal data, never pushed.
- `people/demo/` — fictional profile for OSS contributors. Committed. Created post-validation (Phase 5+, after real users have shaken out bugs). Represents a believable-but-fake AI engineer so contributors can run the full pipeline without writing their own profile first.
- `people/README.md` — contributor onboarding ("create your own `people/{yourname}/` — see `people/demo/` as example").

Shiva can develop Matchbox AND use it for his real job search on the same machine, same clone, without his data entering the repo.

## Decision 4: Anchor packs are profile-level

`people/{name}/anchor-packs.yaml` contains pre-approved bullet variants per role family (FDE pack, SA pack, PM pack, Applied AI pack). Content is person-specific (references their real work at NTT DATA, Pinaka, etc.), so it belongs with the person, not in shared/.

Phase 2 builds anchor-packs.yaml from `people/{name}/profile.yaml:work_history.bullets` — automated extraction where possible, manual curation for the opener variants and narrative beats.

## Decision 5: Schema versioning for profile.yaml

Every profile.yaml carries a version header:

```yaml
_meta:
  schema_version: 1
  last_updated: 2026-04-21
  matchbox_version: 0.2.0
```

The Person loader in Phase 1 inspects `_meta.schema_version`. When Matchbox's schema evolves:
- Add a migration function to `src/matchbox/core/migrations.py`: `def migrate_v1_to_v2(data: dict) -> dict: ...`
- Person loader runs migrations in order: v1 → v2 → v3 → current.
- Migrations are idempotent and never destructive; log what they changed.
- User sees a one-time message on load: "Profile migrated from schema v1 to v2."

Cheap insurance. Essential for OSS users who may not update Matchbox on every release but still want to run their old profile against new code. Without this, schema drift becomes a support nightmare.

## Repo-level vs profile-level decisions (quick-reference table)

| Concern | Level | Location |
|---|---|---|
| Python code | repo | `src/matchbox/*` |
| Scoring rubric schema (dimensions, formula) | repo | `shared/rubric.yaml` |
| Scoring weights (per person) | profile | `people/{name}/profile.yaml:scoring` |
| Voice rules defaults | repo | `shared/voice-rules.yaml` |
| Voice rules overrides | profile | `people/{name}/voice.yaml` |
| Typst template structure | repo | `shared/templates/cv-canonical.typ` |
| Fonts | repo | `shared/fonts/` |
| Search query templates (ATS probe patterns) | repo | `shared/search-templates.yaml` |
| Search query slugs (dream tiers) | profile | `people/{name}/profile.yaml:dream_tiers` |
| Anchor packs (bullet variants per role family) | profile | `people/{name}/anchor-packs.yaml` |
| Dream tiers, exclusions, role_family_preference, compensation | profile | `people/{name}/profile.yaml` |
| Work history, skills, projects | profile | `people/{name}/profile.yaml` |
| Stories (narratives) | profile | `people/{name}/stories.md` |
| Canonical rendered PDFs | profile | `people/{name}/cv-canonical-*.pdf` etc. |
| DB (pipeline state) | profile | `people/{name}/db.sqlite` |
| Runs, reports, output (auto-generated) | profile | `people/{name}/runs/`, `reports/`, `output/` |
| Activity log | profile | `people/{name}/log.md` |
| API keys | local-only | `.env` at repo root (gitignored) |
| CI config | repo | `.github/workflows/ci.yml` |

## UI architecture

One Streamlit instance. Profile switcher in sidebar (same as v0.1 pattern). When user selects a different profile:
- Python disconnects from current `people/{old}/db.sqlite`.
- Reconnects to `people/{new}/db.sqlite`.
- Reloads Person object from `people/{new}/*.yaml`.
- UI widgets refresh to show the new profile's data.

No multi-user auth, no session management. Each person runs their own local Matchbox instance. If multi-tenant SaaS ever becomes a goal, that's a separate architecture discussion (not in scope for v0.2).

## Edge cases handled

**Shiva finds a universally-useful voice rule while tuning his `people/shiva/voice.yaml`.** He promotes it by editing `shared/voice-rules.yaml` as a separate commit. His personal voice.yaml edits stay local. Commit messages distinguish: `feat(voice): add "synergize" to default banned words` vs `(untracked: personal voice tuning)`.

**Profile schema changes in a future Matchbox release.** Migration function handles it (Decision 5). User sees a one-line notice on load.

**Intern shares a machine with Shiva during onboarding.** Each has their own clone with their own `people/{name}/` — separate clones mean separate DBs, separate git configs, separate everything.

**Contributor clones the repo to try Matchbox.** Runs `matchbox init-profile --name demo-alex`, creates `people/demo-alex/` scaffold. Fills in their own data or uses `people/demo/` as a copy-paste starter. Never collides with the committed `people/demo/`.

**A user commits their own profile by accident** (bypassing gitignore). Caught by pre-commit hook in CI: a check that `people/*` contents aren't in the commit (except `demo/` and `README.md`). Phase 5 adds this hook.

## Impact on earlier plan sections

- **Phase 1 additions**: (a) `migrations.py` module for schema versioning; (b) `_meta` block in the migrated profile.yaml; (c) layered voice-rules loader.
- **Phase 4 additions**: (a) `matchbox init-profile --name X` CLI command to scaffold a new profile; (b) pre-commit hook in CI.
- **Phase 5 additions**: (a) `people/README.md`; (b) demo profile creation; (c) schema-version documentation in `docs/architecture.md`.

---
