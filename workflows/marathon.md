---
id: marathon-workflow
purpose: Orchestration brief for the Matchbox marathon scan. Executed by a Sonnet orchestrator invoking Haiku workers across 4 modes x 5 countries with dedup, then Sonnet batched scorers, writing to SQLite.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-21
review_by: 2026-10-21
size_budget: 5000_tokens
---

# Marathon Workflow

Marathon scan produces a large dump of scored jobs from 4 modes x 5 countries = up to 20 scan surfaces, stored in SQLite. See `matchbox/plans/marathon-plan-2026-04-21.md` for strategic context.

This file is the execution brief for the Sonnet orchestrator. Haiku workers handle discovery/filter/fetch. Sonnet handles scoring. Opus only for final diagnostic if the run partially fails.

## Invocation context

The orchestrator receives from `profile-dispatcher.md`:
- `profile_name` (e.g., "shiva")
- `atma_path` (e.g., "atma/people/shiva")
- `matchbox_path` (e.g., "matchbox/people/shiva")
- Flags: `--trial`, `--modes <list>`, `--countries <list>`, `--dry-run`, `--budget-override`

Defaults when flags absent:
- modes: `[dream, roles, startups, niches]` (all four)
- countries: `[india, us, uk, singapore, eu]` (all five)

## Hard limits (read from matchbox/profiles.yml)

- Per-marathon soft cap: $75
- Per-marathon hard stop: $150
- Per-marathon time cap: 120 minutes
- Per-marathon job cap: 500 scored jobs
- Trial cap: $10 per run

If any cap is reached, write PARTIAL digest and stop gracefully.

## Phase 0: Pre-filter

**Worker:** orchestrator (this Sonnet, no delegation)

**Duration:** 30 seconds.

1. Call `db.get_hot_companies(profile, days=14, min_active_apps=3)` - returns list of companies in active cooling.
2. Call `db.existing_urls(profile)` - returns set of URLs already stored (for cross-run dedup).
3. Read `matchbox/people/{profile}/search-queries-jobs.yml` for queries.
4. Read `atma/people/{profile}/wiki/profile.yml` for title filters, geo policy, weights.
5. Record `scan_run_id = db.create_scan_run(profile, mode, country, is_trial)`.

### Soft cooling semantics (updated 2026-04-21)

Hot companies are NOT hard-excluded from discovery. They are still discovered and scored so the user knows what roles exist. The cooling flag prevents:

- **Auto-queuing** for tailoring
- **Auto-promotion** to SURFACED band in digest (shown in a separate "Cooling — new roles at applied-to companies" section instead)

Rationale: the user benefits from knowing new roles exist at the company they just applied to. That data is real value. What we want to prevent is spraying MORE applications to the same company while the first batch is still in pipeline. The softer rule: discover + score + surface-with-warning, but do not auto-batch.

In Phase 5 (digest), hot companies' new roles appear in a dedicated section:

```
## New roles at companies you recently applied to (cooling active)
  - Anthropic: 6 new roles found this scan (scores 4.15-4.80)
    → Recommended: hold for 14 days, then re-evaluate based on initial applications' responses
```

Log to `matchbox/people/{profile}/runs/{date}-marathon/pipeline-log.md`:
```
[Phase 0] hot_companies: [list]
[Phase 0] existing_urls: N
[Phase 0] scan_run_id: {id}
[Phase 0] queries: M country x mode combinations
```

## Phase 1: DISCOVER (Haiku workers, parallel batches)

**Worker:** Haiku subagents, up to 6 in parallel.

**Duration:** 10-25 minutes depending on surface count.

For each (mode, country) combination in selected_modes x selected_countries:

1. Read the corresponding query set from search-queries-jobs.yml (mode determines which section).
2. Apply country geo keywords to each query.
3. Exclude hot_companies (use `-site:{company}` or skip API calls).
4. Execute queries:
   - For mode_1_dream: direct API calls to Greenhouse/Ashby + site searches for non-API companies
   - For mode_2_roles: site searches with country geo scope
   - For mode_3_startups: site searches on YC, HN, platform filters
   - For mode_4_niches: site searches on niche intersections
5. For each result, extract: {company, role, location, url, mode, ats_source}
6. Dedup within surface AND across already-executed surfaces (shared in-memory set).
7. Write per-surface output to `runs/{date}-marathon/discover-{mode}-{country}.json`.

**Cross-surface dedup rule:** normalize (company + role + location) as key. First occurrence wins. Log dropped duplicates to pipeline-log.md.

**Safety:** skip any URL in existing_urls (it's already scored from a prior run). No duplicate scoring.

**Budget check:** after every 4 surfaces, sum Haiku tokens spent. If > 70% of budget, halt Phase 1 early and proceed to Phase 2 with partial results.

## Phase 2: FILTER + COOLING + DEDUP

**Worker:** orchestrator (Sonnet, no delegation - this is fast).

**Duration:** 30 seconds.

1. Merge all `discover-*.json` files.
2. Apply title filter from profile.yml (positive + negative + seniority_boost).
3. Apply geo filter (dream cos bypass; non-dream must be India-or-remote-India).
4. Apply deal_breakers.
5. Apply hot_companies exclusion (belt and suspenders, should already be filtered).
6. Write survivors to `runs/{date}-marathon/phase-2-survivors.json`.

Log counts:
```
[Phase 2] raw_candidates: N
[Phase 2] after title filter: M
[Phase 2] after geo filter: K
[Phase 2] after deal_breakers: J
[Phase 2] survivors written: J
```

## Phase 3: FETCH (Haiku workers, parallel)

**Worker:** Haiku subagents, up to 8 in parallel.

**Duration:** 15-30 minutes.

For each survivor:

1. Prefer structured API response (already fetched in Phase 1 for dream cos).
2. Otherwise fetch the JD URL via WebFetch with prompt: "Extract role overview, responsibilities, required qualifications, preferred qualifications, compensation if stated, visa sponsorship language, posting date. Preserve verbatim phrasing."
3. Write each fetched JD to `runs/{date}-marathon/jds/{id}.md`.

**Timeout:** 30 seconds per fetch. If site blocks bot, fall back to LinkedIn site search for that company+role.

**Budget check:** if > 80% budget spent, halt Phase 3. Any unfetched survivors skip to Phase 5 skip list.

## Phase 4: SCORE (Sonnet, batched)

**Worker:** Sonnet subagents, batches of 10 jobs per call.

**Duration:** 20-40 minutes depending on job count.

For each batch of 10 JDs:

1. Construct single Sonnet prompt with:
   - `atma/shared/scoring-rubric.md` (rubric)
   - Relevant files per job_scoring routing (profile.yml, skills.md, preferences.md, projects.md, log.md#last-30d)
   - 10 JDs with IDs
2. Sonnet returns scored results as JSON array with six sub-scores: `[{id, cv_match, company_mission_fit, role_mission_fit, comp, cultural, red_flags, total, recommendation, role_family, dream_tier, exclusion_triggered, report_text, keywords, tailoring_notes}, ...]`. Leave `north_star` out — that column is legacy. See `matchbox/workflows/score.md` for the exclusion gate and role-family classification rules.
3. For each job in response:
   - Write report Markdown to `reports/jobs/{NNN}-{company-slug}-{date}.md` (include frontmatter)
   - Call `db.insert_job(profile, run_id, ...all fields...)` - SQLite commit per job
4. Log batch completion to pipeline-log.md.

**Budget check:** after every 3 batches (30 jobs), sum cost. Halt if > 95% budget.

**Batched scoring rationale:** one Sonnet call for 10 jobs costs ~$0.15-0.25 (context shared), vs ~$0.08 each if called separately. Savings: 60%.

## Phase 5: DIGEST (Sonnet orchestrator, writes digest)

**Worker:** orchestrator (this Sonnet).

**Duration:** 1 minute.

1. Query db.get_stats(profile) and db.list_jobs(profile, since_date=today, order_by="total_score DESC", limit=30).
2. Write digest to `runs/{date}-marathon/digest.md` with:
   - Summary: counts by phase, budget used, time elapsed
   - Top 30 surfaced roles (score >= 4.0) with company, role, country, score, recommendation
   - Review band (3.5-3.9) count
   - Skipped count + distribution of skip reasons
   - Blocked by hot cooling: list of skipped companies
   - Next actions: "Open the UI: streamlit run matchbox/ui/ui.py"
3. Call `db.complete_scan_run(profile, run_id, ..., status='success')`.

## Phase 6: FINALIZE

1. Log final pipeline-log.md entry.
2. Confirm all files written.
3. Return terse summary to invoker.

## Cost accounting (approximate)

| Phase | Model | Typical cost |
|-------|-------|--------------|
| Phase 0 | Sonnet (trivial) | ~$0.01 |
| Phase 1 | Haiku x 6 parallel x 20 surfaces | ~$3-6 |
| Phase 2 | Sonnet (trivial) | ~$0.02 |
| Phase 3 | Haiku x 8 parallel x 150-300 JDs | ~$5-10 |
| Phase 4 | Sonnet batched, ~30 batches of 10 | ~$15-35 |
| Phase 5 | Sonnet digest | ~$0.50 |
| Orchestration | Sonnet overhead | ~$2-5 |
| **Total** | | **~$25-60** |

Trial variants:
- Trial 1 (mode=dream, country=india): ~$3
- Trial 2 (mode=dream,roles; country=india,uk): ~$8

## Failure modes and recovery

| Failure | Detection | Action |
|---------|-----------|--------|
| Budget cap reached | Sum of per-phase costs > cap | Stop at current phase, write PARTIAL digest |
| Time cap reached (>120 min) | Wall clock | Stop, write PARTIAL digest |
| API down (Greenhouse or Ashby) | 5xx from host | Fall back to LinkedIn site search; log warning |
| Single JD fetch fails | timeout or 4xx | Skip that JD, flag in digest |
| Sonnet batch returns malformed JSON | parse fail | Retry once; if fails again, split batch to 5 + 5 |
| SQLite lock contention | OperationalError | db.py retries with backoff (WAL mode should prevent this) |
| Profile file missing | Dispatcher catches | Fail at dispatch, never reach here |

## SSOT + read-only Atma guarantees

**Marathon NEVER writes to Atma wiki.** It reads:
- `atma/people/{profile}/wiki/profile.yml` (weights, filters)
- `atma/people/{profile}/wiki/skills.md` / `preferences.md` / `projects.md` / `log.md#last-30d`
- `atma/shared/scoring-rubric.md`

Marathon writes:
- `matchbox/people/{profile}/db/matchbox.db` (SQLite)
- `matchbox/people/{profile}/runs/{date}-marathon/**` (state files)
- `matchbox/people/{profile}/reports/jobs/**` (per-role reports)

Never writes to: `atma/**` (any file), `matchbox/people/{profile}/output/**` (tailoring is separate command), `matchbox/people/{profile}/applications.md` (legacy; SQLite is now canonical).

## After marathon completes

User actions:

1. Run `streamlit run matchbox/ui/ui.py --server.port 8501`
2. Open http://localhost:8501 in browser
3. Filter by score >= 4.0, review APPLY band
4. Queue 30-50 jobs for tailoring (UI writes to `queue/tailor-queue.yml`)
5. Invoke the tailor workflow on the queue. Two ways:
   - Claude Code: `/tailor --batch --profile shiva`
   - Any Sonnet session: paste `matchbox/workflows/tailor.md` and say "run in --batch mode for profile shiva"
6. Review tailored CVs and cover letters
7. For each decision to submit: invoke the apply workflow with the job id (e.g. Claude Code: `/apply --id NNN`, or paste `matchbox/workflows/apply.md` into any Sonnet), then submit via company portal

## Trial mode (`--trial`)

When `--trial` flag is set:
- is_trial=1 written to scan_runs (for easy filtering out later)
- Cost cap reduced to $10
- Time cap reduced to 30 minutes
- Only 2-3 surfaces run (not 20) based on `--modes` and `--countries`
- All gates + writes behave normally; this is a real scoring run, just small
- Digest includes "TRIAL RUN" header

## Example invocations

```
/marathon --profile shiva --trial --modes dream --countries india
  - Trial 1 from plan. Expected ~$3, 8 min, 15-30 jobs.

/marathon --profile shiva --trial --modes dream,roles --countries india,uk
  - Trial 2. Expected ~$8, 15 min, 40-80 jobs.

/marathon --profile shiva
  - Full marathon. All modes, all countries. ~$30-60, 45-90 min.

/marathon --profile shiva --modes niches --countries us,uk
  - Niche intersection scan in US + UK. For targeted follow-up.
```
