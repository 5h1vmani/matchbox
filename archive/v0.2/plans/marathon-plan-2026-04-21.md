---
id: marathon-plan-2026-04-21
purpose: Strategic plan for Matchbox marathon scan build. SSOT for what we are building, why, and the trial-then-scale protocol.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-21
review_by: 2026-06-21
size_budget: 4000_tokens
---

# Marathon Scan Plan, 2026-04-21

## Goal

Build and run a scaled Matchbox scan that produces 200-500 scored jobs in a single sweep, stored in SQLite, reviewable via a Streamlit UI, with on-demand tailoring. The end state: Shiva has a filterable pipeline of 300+ quality jobs, picks 150-200 to apply to, and lands 25-30 interviews.

## Success criteria

1. Marathon completes in under 120 minutes
2. Produces >= 150 scored jobs with total_score >= 3.5
3. At least 30 jobs score >= 4.0 (APPLY band)
4. UI renders and filters work end-to-end
5. All artefacts pass the three quality gates (voice lint, factual audit, rendering test)
6. Zero Atma writes (read-only contract holds)
7. Cost under $75 per marathon

## Architecture overview

**4 modes x 5 countries = 20 scan surfaces per run.**

### Modes

| Mode | What it scans | Size |
|------|---------------|------|
| `dream` | 21 curated AI-native dream companies (direct API + site search) | Narrow, precise |
| `roles` | Role-title queries: FDE, Solutions Architect, AI PM, Senior/Staff/Principal PM, Head of Product, DevRel, plus established AI divisions (Google DeepMind, Microsoft AI, Meta AI, Apple Intelligence, Amazon Bedrock), consultancies (McKinsey QuantumBlack, BCG Gamma, Bain Vector), Indian unicorns (Zomato/Swiggy/Flipkart/Meesho) | Adjacent |
| `startups` | Well-funded Series A-C + YC batches + HN "Who is Hiring" + mid-stage platforms (Databricks, Snowflake, MongoDB, Cloudflare, Airtable) | Broader |
| `niches` | Finance x AI, AI x Mission, Coordination x Building intersections | Cross-border rare-combo |

### Countries

| Country | Geo keywords | Visa path | Target cos |
|---------|--------------|-----------|-----------|
| `india` | India, Bangalore, Hyderabad, Mumbai, Delhi, Pune, remote from India | None needed | Sarvam, Krutrim, Razorpay AI, Indian unicorns |
| `us` | United States, San Francisco, New York, Seattle, Austin, Remote US | H-1B lottery / O-1 / employer | Anthropic, OpenAI, Cursor, Sierra, Databricks, Big Tech AI |
| `uk` | United Kingdom, London, Manchester, Edinburgh, Dublin | Skilled Worker (fast) | Anthropic London, Cohere London, major UK AI offices |
| `singapore` | Singapore, Remote APAC | Employment Pass | Sea AI, Grab AI, APAC offices |
| `eu` | Paris, Amsterdam, Stockholm, Berlin, remote EU | Various national visas (often faster than H-1B) | Mistral (Paris), Poolside (Paris), Hugging Face (Paris), Lovable (Stockholm), Klarna AI (Stockholm), Zalando AI (Berlin), Adyen (Amsterdam) |

### Pre-filter (Phase 0, before discovery)

- Read `applications.md` / SQLite for active applications
- Compute `hot_companies`: 3+ active applications in last 14 days
- Skip API calls for hot companies entirely in mode_1
- Add `-site:{hot_company}` to search queries in modes 2-4
- Saves 30-50% tokens on days with active cooling

### Data layer (SQLite)

One file per profile: `matchbox/people/{name}/db/matchbox.db`. Two tables:

- `jobs` - one row per scored job. Includes discovery metadata, JD summary, all 5 scoring dimensions, pipeline state, tailor state, CV/cover paths, timestamps.
- `scan_runs` - audit log per marathon: mode, country, counts at each phase, cost, status.

Access via `matchbox/shared/db.py` - the only file that contains SQL. All agents call Python functions, not raw queries.

### UI layer (Streamlit)

`matchbox/ui/ui.py` - single file, ~200 lines. Run with `streamlit run matchbox/ui/ui.py --server.port 8501`.

Features:
- Table of all jobs with filters (country, mode, state, score range, recommendation, has_cv, date)
- Sortable columns
- Per-row actions: state dropdown, "Queue Tailor" button, "Queue Tailor + Cover", "View Report", "Open JD"
- Bulk actions: select multiple rows, bulk queue for tailoring
- Summary bar: counts by state, cost spent, active cooling companies

UI never calls Claude directly. Writes to `queue/tailor-queue.yml`. User separately runs `/tailor --batch` in Claude Code to process queued jobs.

## File structure (new and modified)

### New files

```
matchbox/
├── plans/
│   └── marathon-plan-2026-04-21.md       (this file)
├── shared/
│   └── db.py                             schema + wrapper functions
├── workflows/
│   └── marathon.md                       orchestration brief (agent-readable)
├── ui/
│   └── ui.py                             Streamlit UI
└── people/shiva/
    ├── db/
    │   └── matchbox.db                   SQLite file (gitignored)
    └── queue/
        └── tailor-queue.yml              UI writes here; /tailor reads

.claude/commands/
└── marathon.md                           new slash command
```

### Modified files

- `matchbox/people/shiva/search-queries-jobs.yml` - add `eu` country keywords, add company sub-sections
- `atma/people/shiva/wiki/profile.yml` - upgrade Mistral/Poolside to dream_companies
- `matchbox/profiles.yml` - new budget caps
- `matchbox/workflows/tailor.md` - add `--batch` mode reading queue
- `.claude/commands/tailor.md` - add `--batch` flag
- `.gitignore` (root) - exclude matchbox.db + queue files

## Budget caps (agreed)

| Cap | Value | Protection |
|-----|-------|-----------|
| Per-marathon soft | $75 | Typical run is $25-35; 2x headroom |
| Per-marathon hard stop | $150 | Prevents runaway |
| Per-marathon time | 120 minutes | Absolute wall time |
| Per-marathon job cap | 500 scored | Prevents DB bloat |
| Monthly total | $300 | Supports 2-3 marathons + daily scans + ~60 tailored apps |
| Tailor batch | $20/run | 30 tailored CVs per approval |

## Trial-then-scale protocol

### Trial 1 — Minimum viable end-to-end

```
/marathon --profile shiva --modes dream --countries india --trial
```

**Expected:** 15-30 scored jobs, ~$3, ~8 minutes. Validates schema writes, scoring pipeline, SQLite access, UI render.

**Review gates:** User opens UI, confirms:
1. All jobs show up
2. Filters work
3. State dropdowns update DB correctly
4. Scoring distribution looks sane (not everything 3.5)
5. Report links open

If Trial 1 passes, advance. If not, fix and re-run.

### Trial 2 — Multi-country + multi-mode

```
/marathon --profile shiva --modes dream,roles --countries india,uk --trial
```

**Expected:** 40-80 scored jobs, ~$8, ~15 minutes. Validates cross-surface dedup, non-API searches, realistic scoring.

**Review gates:**
1. No duplicates across modes/countries
2. UK roles have UK locations
3. Rubric correctly surfaces higher scores for known-fit roles
4. Cost tracking matches SQLite scan_runs entry

If Trial 2 passes, advance to full marathon.

### Full marathon

```
/marathon --profile shiva
```

**Expected:** 200-500 scored jobs, ~45-90 minutes, ~$30-60. All 20 scan surfaces. Produces the pipeline of quality jobs.

**Post-run:** User reviews UI, filters by score >= 4.0, queues 30-50 for tailoring. `/tailor --batch` processes queue.

## Engineering principles applied

| Principle | How |
|-----------|-----|
| SSOT | SQLite is single truth for pipeline; Atma is single truth for identity; db.py owns all SQL |
| DRY | Queries live once (search-queries-jobs.yml); scoring rubric lives once (atma/shared/scoring-rubric.md); no schema duplication |
| Single responsibility | db.py persists, marathon.md orchestrates, score.md scores, tailor.md tailors, ui.py displays |
| Least privilege | Scorer sees only JD + minimal profile; UI is read + state-update only; Agents call functions not raw SQL |
| Fail closed | DB write errors halt pipeline; missing frontmatter makes files invisible; unknown tasks return empty |
| Auditability | scan_runs logs every marathon; jobs has created_at/updated_at; agents write to pipeline-log.md |
| Budget safety | Hard stops at cost cap, time cap, job count cap |
| Read-only Atma | Marathon never writes to Atma wiki; only /apply writes (via ingest protocol) |

## Known risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Scoring quality degrades with larger batches | Batch size cap 10 jobs per Sonnet call; trials validate on small batches first |
| SQLite contention with concurrent Haiku workers | Serialize writes through db.py transactions; parallelize reads |
| Query overlap between countries (company opens office in 2 places) | Dedup key = company + exact role title + location; location variance is a feature not a bug |
| Budget exceeded mid-run | Soft cap alerts at 70%; hard stop at 100%; partial digest written |
| API rate limits (Greenhouse/Ashby) | Throttle to 1 req/sec per host; retry with exponential backoff max 3 attempts |
| UI crashes mid-review | Streamlit reloads cleanly; DB state persists |
| User queues too many tailors | `/tailor --batch` has own $20 cap; stops gracefully |

## Timeline

**Today (2026-04-21):**
- Phase A (infrastructure): 45-60 min build
- Phase B (config): 15 min
- Phase C (migration): 10 min
- Phase D (Trial 1): 8 min run + user review
- Phase E (Trial 2): 15 min run + user review
- Phase F (Full marathon): 60-90 min run
- Total: ~3-4 hours

**This week:**
- User reviews SQLite pipeline via UI
- Queues 30-50 tailored CVs
- Runs `/tailor --batch` in Claude Code
- Submits top-priority applications

**Next 3-4 weeks:**
- Daily dream scans maintain fresh discoveries
- User processes tailor queue and submits 50-70 more applications
- Target: 25-30 interviews by end of week 4

## Open items (known future work, not blocking)

1. `/discover-niche` standalone command (weekly reasoning-based niche surface)
2. Recruiter response tracking via email integration
3. Analytics dashboard (apply -> screen -> interview conversion rates)
4. Cost trending over time
5. Multi-person UI (currently single profile per run)
6. Interview scheduling integration
7. Rejection pattern analysis (which role types keep getting rejected)

## Files this plan governs

This plan is the strategic SSOT for the marathon build. Do not duplicate the content above into workflow files or code comments. Reference this plan from other files instead.

Workflows that implement this plan:
- `matchbox/workflows/marathon.md` - orchestration for agent execution
- `matchbox/shared/db.py` - schema and functions this plan describes
- `matchbox/ui/ui.py` - UI this plan specifies
- `.claude/commands/marathon.md` - slash command entry point
