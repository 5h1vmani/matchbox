# Commands Reference

All Matchbox slash commands, flags, and invocation patterns.

**Important:** slash commands are run in **Claude Code** (the chat window), not in your terminal. Your terminal is only for `streamlit run ...` and occasional filesystem work.

## `/scan-jobs`

Daily scan: discovers new roles, scores them, does NOT auto-tailor.

### Flags

| Flag | Values | Default | Purpose |
|------|--------|---------|---------|
| `--profile` | string | `shiva` (from profiles.yml) | Which person to run for |
| `--mode` | dream / roles / startups / niches / all | all | Which query mode(s) to use |
| `--country` | india / us / uk / singapore / eu / australia / canada / new_zealand / all | all | Geo scope |
| `--date` | YYYY-MM-DD | today | Override the run date |
| `--dry-run` | flag | false | Plan only; no DB writes |
| `--phase` | integer | all | Resume from specific phase (debug) |
| `--override-cooling` | company | none | Ignore cooling filter for one company |

### Examples

```
/scan-jobs --profile shiva --mode dream --country india
  Cheapest daily run. 21 dream companies filtered to India. ~$0.30, 5 min.

/scan-jobs --profile shiva --mode roles --country us
  US-based role searches. Excludes dream cos already known. ~$0.40.

/scan-jobs --profile shiva --mode niches
  Finance x AI, AI x Mission, Coordination x Building. Cross-border. ~$0.50.

/scan-jobs --profile shiva
  All 4 modes x all countries. Roughly equal to a mini-marathon. ~$2-4.

/scan-jobs --profile shiva --dry-run
  Validates queries + pre-filter without writing. Useful for config testing.

/scan-jobs --profile shiva --override-cooling anthropic
  Includes Anthropic this run even though it has 3+ active apps.
```

### What it does

1. Dispatcher validates profile, reads config, creates scan_run row in SQLite
2. Phase 0: pre-filter (hot companies, existing URLs)
3. Phase 1: discover via APIs + search queries (Haiku)
4. Phase 2: dedup + filter + geo (Haiku)
5. Phase 3: fetch JDs for survivors (Haiku)
6. Phase 4: score with 5-dim rubric (Sonnet, batched 10 per call)
7. Phase 5: write digest, finalise scan_run

Output: new rows in SQLite `jobs` table, per-role reports in `reports/jobs/`, digest at `runs/{date}-daily-jobs/digest.md`.

## `/marathon`

Big sweep: 4 modes x 5+ countries in one invocation.

### Flags

Same as `/scan-jobs`, plus:

| Flag | Values | Purpose |
|------|--------|---------|
| `--trial` | flag | Small trial run, cost cap $10, time cap 30 min |
| `--budget-override` | USD | Raise the per-run cap for this invocation |

### Examples

```
/marathon --profile shiva --trial --modes dream --countries india
  Trial 1 minimum viable. $3, 8 min, 15-30 jobs.

/marathon --profile shiva --trial --modes dream,roles --countries india,uk
  Trial 2. $8, 15 min, 40-80 jobs.

/marathon --profile shiva
  Full marathon, all modes, all countries. $30-60, 45-90 min, 150-400 jobs.

/marathon --profile shiva --modes startups,niches --countries canada,australia
  Targeted expansion. $8-15, 20-30 min.
```

### Budget caps (from profiles.yml)

- Soft cap: $75
- Hard stop: $150
- Time cap: 120 min
- Job cap: 500

## `/tailor`

Produce tailored CV (and optional cover letter) for a specific job or a batch.

### Flags

| Flag | Values | Purpose |
|------|--------|---------|
| `--profile` | string | Which person |
| `--id` | integer | Specific job ID to tailor |
| `--batch` | flag | Process up to 20 from the tailor-queue.yml |
| `--with-cover` | flag | Also produce cover letter |
| `--cover-only` | flag | Only cover letter (CV must already exist) |
| `--dry-run` | flag | Preview without writing |

### Examples

```
/tailor --id 135 --profile shiva
  CV only for job 135.

/tailor --id 135 --profile shiva --with-cover
  CV + cover letter for job 135.

/tailor --batch --profile shiva
  Process all jobs in queue (up to 20). Reads queue/tailor-queue.yml.

/tailor --batch --profile shiva --dry-run
  Preview which jobs would be tailored; no writes.
```

### Quality gates (all MUST pass)

1. **Rendering test** — PDF must be exactly 2 pages (CV) or 1 page (cover)
2. **Factual audit** — 7 checks for honesty (no private-repo public claims, no inflated numbers, etc.)
3. **Voice lint** — 0 em dashes, 0 contractions, 0 banned phrases

If any gate fails, the tailor is rejected and the run returns an error pointing to the violation.

### Output path

```
matchbox/people/{profile}/output/jobs/{today's date}/
├── pdfs/
│   ├── cv-{company-slug}-{role-slug}.pdf
│   └── cover-{company-slug}-{role-slug}.pdf
└── html/
    ├── cv-{company-slug}-{role-slug}.html
    └── cover-{company-slug}-{role-slug}.html
```

Budget: $20 per invocation. Takes 15-30 min for a full batch.

## `/apply`

Log an application submission. Updates DB state + writes to Atma log.

### Flags

| Flag | Values | Purpose |
|------|--------|---------|
| `--profile` | string | Which person |
| `--id` | integer | The job ID being submitted |
| `--notes` | string | Extra context (referral, portal used, etc.) |

### Examples

```
/apply --id 135 --profile shiva
  Basic submission log.

/apply --id 135 --profile shiva --notes "Applied via Greenhouse. Referral from Priya."
  With context.
```

### What it does

- Updates DB: state `tailored` → `applied`, stamps `applied_date`
- Writes entry to `atma/people/shiva/wiki/log.md` via ingest protocol (the 5-question ritual)
- Appends to `applications.md` (legacy export, still maintained)

### Preconditions

- Job must be in state `tailored` or `evaluated` (not already `applied`)
- Tailored CV must exist at the path from the DB
- Atma log.md must be writable

## `/onboard-profile`

Initialise a new person in the Matchbox + Atma system.

### Flags

| Flag | Values | Purpose |
|------|--------|---------|
| `--name` | string (required) | Profile name (lowercase, no spaces) |
| `--tracks` | jobs,programs | Which tracks to enable |
| `--mode` | passive/warm/active | Operating mode |

### Examples

```
/onboard-profile --name brother --tracks jobs --mode active
  New profile for a brother, job search only.

/onboard-profile --name intern_ananya --tracks jobs --mode active
  Intern profile, jobs enabled, active mode.
```

### What it does

1. Creates `atma/people/{name}/` with full template structure
2. Creates `matchbox/people/{name}/` with mode.yml, search-queries, etc.
3. Registers profile in `matchbox/profiles.yml` with `enabled: false`
4. Starts the Identity Interview (conversational, 30-45 min)

After onboarding, user must:
- Complete Identity Interview
- Review templates, fill in TODOs
- Set `enabled: true` in profiles.yml
- Run their first `/scan-jobs` or `/marathon`

## UI actions (no slash command, browser buttons)

These happen in Streamlit at http://localhost:8501:

- **State dropdown per row** — change state manually (e.g., rejected, responded, offer)
- **📝 CV button** — queue job for CV-only tailor
- **📝+✉ button** — queue job for CV + cover letter tailor
- **⏪ Unqueue button** — remove job from queue, state back to evaluated
- **📤 Mark Submitted button** (new) — update DB state to applied + applied_date (still run /apply in Claude Code to write to Atma log)
- **"Exclude company" multi-select** — hide specific companies this session
- **"Hide cooling companies" checkbox** — hide companies with 3+ recent apps

## File paths cheat sheet

| Path | Contents |
|------|----------|
| `matchbox/people/shiva/db/matchbox.db` | SQLite pipeline state |
| `matchbox/people/shiva/queue/tailor-queue.yml` | Jobs waiting for /tailor --batch |
| `matchbox/people/shiva/output/jobs/{date}/pdfs/` | Tailored CVs and covers (submit these) |
| `matchbox/people/shiva/output/jobs/{date}/html/` | HTML sources (edit if needed) |
| `matchbox/people/shiva/reports/jobs/{NNN}-*.md` | Per-role evaluation reports |
| `matchbox/people/shiva/runs/{date}-*/digest.md` | Per-run summary |
| `atma/people/shiva/wiki/cv.md` | Master CV (source of truth, edit with care) |
| `atma/people/shiva/wiki/log.md` | Your activity log (auto-updated by /apply) |

## Budget caps (from profiles.yml)

| Routine | Soft cap | Hard stop |
|---------|----------|-----------|
| Daily scan | $2.00 | - |
| Marathon | $75.00 | $150.00 |
| Trial marathon | $10.00 | $10.00 |
| Tailor batch | $20.00 | $20.00 |
| Monthly total | $300.00 | - |

Adjust in `matchbox/profiles.yml` if you need more headroom.
