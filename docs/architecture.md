# Architecture

Why Matchbox is built the way it is. Read once; reference when something confuses you.

## Two layers: Atma (identity) + Matchbox (pipeline)

```
atma/              IDENTITY — slow-changing, you own it
  atma.md          protocol + philosophy
  shared/
    rubric-jobs.yml          the scoring weights (same for everyone)
    cv-template.html         HTML template with base64 fonts
    cover-letter-template.html
    ai-detection-guide.md    voice rules
    fonts/                   .ttf files for CV rendering
  people/shiva/
    index.md                 routing: where to find what
    routing.md               pointer file for agents
    sensitivity.md           what is redacted vs public
    wiki/
      profile.yml            targets, comp, dream companies
      cv.md                  master CV (source of truth)
      narrative.md           positioning, one-liners
      voice.md               your style rules
      skills.md              what you actually know
      projects.md            Pinaka, Kubera, past work
      story-bank.md          STAR+R examples for interviews
      preferences.md         font, formality, etc.
      log.md                 auto-written activity log

matchbox/          PIPELINE — fast-changing, tool-owned
  plans/           strategic plans (one-time reference)
  docs/            these guides
  shared/
    db.py          SQLite access layer (the ONLY file with SQL)
  workflows/       briefs for agents (scan, score, tailor, apply)
  ui/ui.py         Streamlit review UI
  profiles.yml     which profiles are active, budget caps
  people/shiva/
    db/matchbox.db         SQLite pipeline state
    search-queries-jobs.yml 4 modes × 8 countries of search terms
    queue/tailor-queue.yml  jobs waiting for batch tailor
    output/jobs/{date}/     tailored CVs and covers
    reports/jobs/{NNN}-*.md per-role evaluation reports
    runs/{date}-*/          per-run artifacts (digests, logs)
```

### Golden rule

**Matchbox reads Atma. Matchbox writes only to Matchbox, with one exception: the ingest protocol (writing to `log.md` when you run `/apply`).**

This separation exists because:
- Identity changes slowly (months between edits to cv.md)
- Pipeline changes fast (new jobs daily, new state transitions hourly)
- Mixing them means a bad tailor run could corrupt your master CV, or a DB reset would wipe your identity

Ingest protocol is the one exception: an application is a real-world event that belongs in your log, not just the pipeline DB.

## Why SQLite as SSOT (Single Source of Truth)

Before SQLite, the pipeline used markdown files:
- `applications.md` — a table of submissions
- `reports/jobs/*.md` — per-role reports
- Filesystem directories for state

This broke at scale (>100 jobs):
1. **Concurrent access:** a marathon scan + a tailor batch + the UI all trying to edit a markdown file → conflicts
2. **Querying:** "show me all India jobs scored ≥ 4.0 in niches mode" requires parsing hundreds of files
3. **Atomicity:** a crash mid-write leaves a half-edited markdown file
4. **Dedup:** checking if a URL is already in the pipeline means reading every file

SQLite solves all four. WAL mode (Write-Ahead Logging) allows concurrent readers + one writer without blocking. Schema-level constraints (UNIQUE on url) prevent duplicate inserts. A single file (`matchbox.db`) is atomic to back up or reset.

**The contract:** only `matchbox/shared/db.py` contains SQL. Everything else (workflows, UI, slash commands) calls functions from that module. This means schema changes are localized.

### Schema summary

Two tables:
- `jobs` — one row per (URL, discovery time). Columns: identity (company, role, url), scoring (5 dims + total), location + comp + visa, state machine (evaluated → applied → offer), pipeline metadata (run_id, discovered_at, queued_at, tailored_at, applied_at), tailor outputs (cv_path, cover_path), link health (url_last_checked, url_http_status — to be added).
- `scan_runs` — one row per invocation of /scan-jobs or /marathon. Tracks mode, country, cost, phase counts, status. Lets you see "which run found this job" and "what did each run cost."

State machine:
```
evaluated → queued_for_tailor → tailored → applied
                                              ↓
                                          responded → interview → offer
                                              ↓                     ↓
                                          rejected            accepted/declined

Terminal: discarded (agent removed), skip (you dismissed)
```

Valid states enforced in Python (`VALID_STATES` set in db.py), not as a DB enum, so new states can be added without schema migration.

## Scan pipeline: 6 phases, 5-layer funnel

```
Phase 0: Pre-filter     → skip companies with existing scored URLs this week
Phase 1: Discover       → ATS APIs + search queries (Haiku)
Phase 2: Filter + dedup → geo filter, existing-URL filter, relevance filter
Phase 3: Fetch JDs      → HTTP/HTML fetch for survivors only
Phase 4: Score          → 5-dim rubric, Sonnet batched (10 jobs/call)
Phase 5: Digest + finalise → write markdown digest, close scan_run row
```

Cost scales up through the funnel:
- Discovery (Haiku, cheap) touches 500-1000 candidates
- Filter (Haiku, cheaper per token) culls to 100-200
- Fetch (free, just HTTP) applies to survivors
- Score (Sonnet, expensive) runs on 100-150
- Tailor (Sonnet with gates, most expensive) runs on 15-25 you manually pick

The reason scoring uses Sonnet and not Opus: Sonnet is ~5x cheaper and matches Opus on classification tasks. Opus is reserved for creative work (not in this pipeline).

The reason tailoring uses Sonnet: voice consistency. Haiku regresses to corporate-speak; Opus is overkill. Sonnet with strong system prompts + voice lint gates produces the right tone.

## The 5-dimension scoring rubric

From `atma/shared/rubric-jobs.yml`:

| Dimension | Weight | What it measures |
|-----------|-------:|------------------|
| cv_match | 0.20 | Keyword + skill overlap between JD and cv.md |
| north_star | 0.30 | Fit with your stated mission (Anthropic/AI safety/coordination) |
| compensation | 0.15 | Comp band fit for your geo + level |
| cultural | 0.20 | Team structure, tooling, values match |
| red_flags | 0.15 | Inverted — penalizes churn, vague role, bad reviews |

Total = weighted sum, max 5.0.

**Band thresholds:**
- ≥ 4.2 → APPLY (strong fit; CV + cover)
- 4.0-4.2 → APPLY (CV only; cover if portal asks)
- 3.5-3.9 → REVIEW (leave for end of week or skip)
- < 3.5 → SKIP (low signal)

Weights live in `atma/people/{profile}/wiki/profile.yml:scoring` (per-profile) or fall back to `atma/shared/rubric-jobs.yml` (default). Override per-profile if your north star is different (e.g., a designer might weight cultural higher than cv_match).

**Why 5 dimensions, not 10?** Each one must be independently explainable. If you can't look at a report and say "this got 3.0 on cultural because X," the dimension is noise. 5 is the most we can defend.

## The font system

CV rendering chain:
1. Markdown (`cv.md`) → tailored markdown → HTML via Python template substitution (`cv-template.html`)
2. HTML with base64-embedded `.ttf` fonts (not external URLs — Chrome offline rendering needs embedded)
3. Chrome headless (`--print-to-pdf`) → PDF

Fonts are base64'd into the HTML at render time so:
- The PDF is fully self-contained (no font substitution on the recipient's machine)
- Rendering works offline
- No Google Fonts CDN call (privacy + reliability)

Default font: **Atkinson Hyperlegible** (letterform clarity, strong bold weights, designed for readability).
Alternatives: **IBM Plex Sans** (corporate signal), **Manrope** (modern startup signal).

Font selection is per-profile (`preferences.font` in profile.yml). Font files sit in `atma/shared/fonts/`. Config registry: `atma/shared/fonts/font-config.yml` maps font keys to filenames and CSS weights.

### Why not WeasyPrint or ReportLab?

Both generate PDFs directly from Python, no Chrome needed. But:
- WeasyPrint CSS support is incomplete (Grid partially, Flexbox with bugs)
- ReportLab requires reimplementing typography from scratch

Chrome headless renders exactly what a browser renders, which is the platform designers target. The 2-page constraint is enforced via page-break CSS rules that Chrome handles correctly.

Cost: ~100ms per PDF, and Chrome is already installed on macOS dev machines.

## 4 modes × 8 countries

Scan queries are structured as 4 semantic modes:

| Mode | Meaning | Example query |
|------|---------|---------------|
| dream | Known target companies | `site:jobs.anthropic.com` |
| roles | Role-centric search | `"solutions architect" AI SaaS` |
| startups | Funded early-stage | `YC W26 batch AI safety hiring` |
| niches | Cross-domain intersections | `"finance × AI" coordinator role` |

And 8 geographies: india, us, uk, singapore, eu, australia, canada, new_zealand.

**Why 4 modes, not 1 general scan?** Different modes produce different tails. A pure keyword scan misses dream companies that don't advertise on aggregators. A dream-only scan misses serendipitous role discoveries at companies you've never heard of. Niches find the cross-domain roles that match your unusual profile (finance + AI + coordination).

**Why 8 countries, not just India + US?** Anthropic has London + Dublin offices. Singapore has lower CoL for the same comp. AU/NZ/CA have favorable visa paths. Excluding a geo means excluding opportunities; your filter is already tight (comp band + mission fit), so geography expansion is free.

Queries live in `matchbox/people/{profile}/search-queries-jobs.yml` as `modes.{mode}.countries.{country}.queries: [...]`. The marathon workflow iterates mode × country and executes each list.

## Soft cooling filter

A company with 3+ active applications in the last 14 days is "cooling."

**Hard cooling (rejected approach):** exclude from scan, never re-surface.
- Problem: you might miss a new role at that company that is different enough to warrant another shot.

**Soft cooling (adopted approach):** company stays in scan, but the UI flags it. Your default filter hides cooling companies; toggle to show them.

Implementation:
- Scan phase 0 counts applied_date records in last 14 days per company
- UI filter "Hide cooling companies" (on by default)
- Override flag `--override-cooling anthropic` forces one scan to include it

This protects against spam without blocking signal. If Anthropic posts a brand-new role you care about, untick the filter for that session.

## Three quality gates on tailored output

Tailoring uses a 10-step workflow (`matchbox/workflows/tailor.md`). After generation, three gates run before the output is saved:

1. **Rendering test:** render to PDF with Chrome. Read PDF page count. CV must be exactly 2 pages; cover must be 1 page. If not, reject the tailor.

2. **Factual audit:** 7 specific checks for honesty violations:
   - Private repo claimed public
   - Inflated metrics (e.g., "100K users" when it was a load test)
   - Implied timeline that contradicts cv.md
   - "Spearheaded" / "championed" / banned verbs
   - First-person plural ("we achieved") misrepresenting solo work
   - Awards or certifications not in story-bank.md
   - Company-specific claims (founders, funding) that aren't in public record
   
   Each check has regex or keyword patterns. Any hit → reject.

3. **Voice lint:** mechanical checks via `grep`:
   - 0 em dashes (`—`)
   - 0 contractions (`don't`, `won't`, etc.)
   - 0 banned phrases (list in `atma/shared/ai-detection-guide.md`)
   
   Fails → reject.

If any gate rejects, the tailor run stops and the user is told which specific gate failed with line numbers. No silent pass-throughs.

**Why three gates, not five or seven?** Each gate catches a distinct failure mode:
- Rendering = layout bug (CV grew too long)
- Factual = honesty violation (agent hallucinated)
- Voice = tone drift (agent regressed to corporate-speak)

Adding more gates (e.g., keyword density, reading level) increases false rejects without catching more real failures. These three are the defended minimum.

## Budget enforcement

From `matchbox/profiles.yml`:

- Daily scan: ~$2.00 soft (no hard stop — daily runs are cheap)
- Marathon: $75 soft, $150 hard stop
- Trial marathon: $10 hard cap
- Tailor batch: $20 hard cap
- Monthly total: $300 soft cap (hard stop would block active search; left as warning)

Enforcement is in the dispatcher (each slash command's first action). It reads `profiles.yml`, checks the running `scan_runs.cost_usd` aggregate for this month, and refuses to start if the cap is hit. Mid-run enforcement is via the job-level Sonnet batch: each batch of 10 jobs costs ~$0.15, so a full marathon is ~500 batches = ~$75.

Override via `--budget-override N.NN` on the command line for one run.

## Read-only Atma contract (enforced how?)

The golden rule "Matchbox reads Atma, writes only via ingest" is not enforced by filesystem permissions (that would be brittle). It is enforced by convention:

1. No function in `matchbox/shared/db.py` writes to a path starting with `atma/`
2. Every workflow brief (`matchbox/workflows/*.md`) has a section titled "Files you may read" (lists Atma paths) and "Files you may write" (lists only Matchbox paths + `atma/people/*/wiki/log.md`)
3. The ingest protocol is the one exception: it is implemented in `matchbox/workflows/apply.md` and writes to `log.md` using the 5-question ritual (see `atma/atma.md` for the protocol spec)

If an agent tries to write outside this boundary, it is a bug. Not a security violation (you control the filesystem), but a design regression. Report it.

## Engineering principles

These are the non-negotiables that shaped every design choice:

1. **Single source of truth:** SQLite for pipeline state. No syncing between markdown and DB.

2. **Localized complexity:** SQL lives in one file. CSS lives in one template. Scoring weights live in one YAML. Find and change in one place.

3. **Budget is a first-class concept:** every command has a cost cap. No invisible escalation.

4. **Human-in-the-loop on submission:** the tool never submits for you. It prepares artifacts; you click Apply.

5. **Honesty over polish:** factual audit gates block tailoring rather than produce a polished-but-untrue CV.

6. **Read Atma, write Matchbox:** identity data is precious and should not be damageable by pipeline bugs.

7. **Claude Code for agentic work, UI for review:** the terminal and browser are for human tasks (launching, reviewing). Claude Code is for agent tasks (scan, score, tailor, apply). No mixing.

8. **Fail loudly, recover quickly:** errors surface immediately with specific file paths and line numbers. The DB can be reset in one command. State transitions are reversible via the UI.

## What Matchbox is not

- **Not an auto-applier.** Never will be. Submission is human.
- **Not an ATS CRM.** We track enough to not miss follow-ups. We don't track recruiter LinkedIn URLs or calendar invites.
- **Not a coaching tool.** It doesn't tell you what jobs to want. It executes on targets you defined in profile.yml.
- **Not shareable.** The DB contains your rejection reasons, salary expectations, and private notes. It is gitignored.
- **Not a resume builder.** cv.md is the source of truth, edited by you. Matchbox tailors around it; it does not generate it.

## When to read this doc again

- Before adding a new workflow (understand the layer boundaries)
- Before changing the schema (understand why columns exist)
- Before changing scoring weights (understand the 5 dimensions)
- After a failure you don't understand (trace it to a principle)
- Never for daily operation (use operator-runbook.md instead)
