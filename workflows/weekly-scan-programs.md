---
id: weekly-scan-programs
purpose: Orchestration brief for Sonnet. Runs the weekly VC-programs scan (FiR / EIR / accelerators / fellowships). Same structure as daily-scan-jobs.md, different artefacts and cadence.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-20
review_by: 2026-10-20
size_budget: 4000_tokens
---

# Weekly Scan Programs Orchestration Brief

You are the Sonnet orchestrator for Shiva's weekly scan of investor programs (Founder-in-Residence, Entrepreneur-in-Residence, accelerators, fellowships). This runs less often than the jobs scan because programs operate on cohort cycles, not rolling postings. Most programs open 1-2 windows per year.

## Invocation

- **Automated:** Claude Code scheduled task, Monday 08:00 IST weekly
- **Manual:** `/scan-programs` slash command

## Key Differences from Daily Jobs Scan

| Aspect | Daily Jobs | Weekly Programs |
|--------|-----------|-----------------|
| Cadence | Daily | Weekly (Monday) |
| Discovery | Greenhouse/Ashby/LinkedIn APIs | Program websites + VC blog/press monitoring |
| Volume | 30-80 raw hits per day | 3-10 programs checked, 0-2 new windows per week |
| Output artefacts | CV + cover letter | Founder essay + venture thesis + deck outline |
| Tailor threshold | Score ≥ 3.5 | Score ≥ 4.0 (programs are scarce, higher bar) |
| State machine | evaluated → applied → responded → interview → offer | evaluated → applied → interviewed → accepted / rejected / waitlisted |

## Inputs

1. `matchbox/people/shiva/search-queries-programs.yml` — curated dream_programs list
2. `atma/people/shiva/wiki/profile.yml` — scoring weights, constraints
3. `atma/people/shiva/wiki/narrative.md` — founder story (used heavily for essay drafts)
4. `atma/people/shiva/wiki/projects.md` — venture details (used for thesis)
5. `atma/people/shiva/wiki/traction.md` — metrics (used in thesis + deck)
6. `atma/people/shiva/wiki/story-bank.md` — narrative material
7. `matchbox/people/shiva/applications.md` — existing pipeline
8. `atma/shared/founder-essay-template.md` — essay structure
9. `atma/shared/venture-thesis-template.md` — thesis structure
10. `atma/shared/scoring-rubric.md`
11. `matchbox/shared/states.yml`

## Output Artefacts

Per run, write to `matchbox/people/shiva/runs/YYYY-MM-DD-weekly-programs/`:

```
runs/YYYY-MM-DD-weekly-programs/
├── phase-1-discover.json
├── phase-2-filter.json
├── phase-3-fetch.md
├── phase-4-score.md
├── phase-5-draft.md          (essay + thesis + deck outline per high-scoring program)
├── pipeline-log.md
└── digest.md
```

Production artefacts go to `matchbox/people/shiva/output/programs/`. Format for each program:
- `essay-{program-slug}-{YYYY-MM-DD}.md`
- `thesis-{program-slug}-{YYYY-MM-DD}.md`
- `deck-outline-{program-slug}-{YYYY-MM-DD}.md`

Scoring reports go to `matchbox/people/shiva/reports/programs/{NNN}-{program-slug}-{YYYY-MM-DD}.md`.

## Budget

- Maximum 60K tokens per run
- Maximum $1.50 USD per run

## Phase-by-Phase

### Phase 1: DISCOVER (Haiku)

**Delegate to Haiku:**

> Read `matchbox/people/shiva/search-queries-programs.yml`. For each program in `dream_programs`, check the program's landing page URL for a current cohort / application window status. For each `search_query`, run a web search.
>
> Return JSON: `[{program_name, program_type (fir/eir/accelerator/fellowship), url, application_window_status (open/closed/rolling/unknown), deadline_if_known, cohort_start_date, source}]`. Budget: 5K tokens.

**Write to:** `phase-1-discover.json`

**Expected count:** 5-15 programs surveyed; 0-3 with open windows per week.

### Phase 2: DEDUP + FILTER (Haiku)

**Delegate to Haiku:**

> Read `phase-1-discover.json`. Read `applications.md` (extract applications where track=program). Read `profile.yml:geography_policy` and constraints.
>
> For each program:
> 1. **Dedup:** if already applied (per applications.md), drop.
> 2. **Window filter:** drop programs with status `closed` and no upcoming window within 90 days.
> 3. **Stage filter:** drop programs requiring seed+ companies with traction metrics Shiva does not meet.
> 4. **Geo filter:** per profile.yml geography_policy. India-local always passes. Others require `willing_to_relocate_if_sponsored` check.
> 5. **Deal-breakers:** drop per profile.yml deal_breakers.
>
> Return survivors list with dropped_count by reason.

**Write to:** `phase-2-filter.json`

### Phase 3: FETCH (Haiku)

**Delegate to Haiku:**

> For each survivor, fetch the full program details: application requirements, evaluation criteria, timeline, cohort size, alumni examples, stipend/equity terms, in-residence commitment (remote/hybrid/on-site), mentor network, demo day format.
>
> Also fetch 2-3 recent blog posts or founder testimonials if available, to gather signal on cultural fit.
>
> Return a markdown file with one `## {Program Name}` section per survivor.

**Write to:** `phase-3-fetch.md`

### Phase 4: SCORE (Sonnet - you do this)

Use the same 5-dimension rubric from `atma/shared/scoring-rubric.md` but with **program-specific weight bias**:

| Dimension | Weight (jobs, default) | Weight (programs, recommended) |
|-----------|------------------------|-------------------------------|
| CV Match | 0.20 | 0.15 (building track record matters, but stage fit matters more) |
| North Star Alignment | 0.30 | 0.35 (programs are 6-12 month commitments - fit matters) |
| Compensation | 0.15 | 0.10 (programs pay stipends; comp is secondary) |
| Cultural Signals | 0.20 | 0.25 (mentor network, alumni, cohort quality are key) |
| Red Flags | 0.15 | 0.15 |

**Apply these weights mentally for programs unless `profile.yml` has a `scoring_programs` section (it does not yet; add later if needed).**

For each program, write a report to `matchbox/people/shiva/reports/programs/{NNN}-{program-slug}-{YYYY-MM-DD}.md` with:
- Legitimacy (high / caution / closed)
- Dimension scores + evidence
- Weighted total
- Recommendation (APPLY / REVIEW / SKIP)
- Application requirements checklist (what needs to be drafted)
- Deadline tracking

Append to applications.md: `track=program`, state `evaluated`.

### Phase 5: DRAFT ARTEFACTS (Sonnet, conditional on score ≥ 4.0)

For each qualifying program, produce **three artefacts**:

**1. Founder Essay** (using `atma/shared/founder-essay-template.md`)

Read the program's essay prompt (from Phase 3 fetch). Adapt the Atma founder narrative to answer the specific prompt. Use the three stories from story-bank.md most relevant to the program's ethos.

Output: `matchbox/people/shiva/output/programs/essay-{program-slug}-{YYYY-MM-DD}.md`

**2. Venture Thesis** (using `atma/shared/venture-thesis-template.md`)

Fill in the thesis template for Pinaka / Vidhar using data from projects.md + traction.md + log.md. Include:
- Problem statement (NEET access gap; coaching center incentive misalignment)
- Approach (behavioral + psychometric analytics for D2C personalized study plans)
- Current state (load-tested to 250K CCU, D2C beta for NEET, pivot from B2B)
- Market size and moat hypothesis
- Team (solo + AI agents for now)
- Ask from the program (funding, mentorship, network, distribution)

Output: `output/programs/thesis-{program-slug}-{YYYY-MM-DD}.md`

**3. Deck Outline** (skeletal, not a full deck)

10-12 slide outline with bullet content per slide. Founder is expected to design the actual deck separately.

Output: `output/programs/deck-outline-{program-slug}-{YYYY-MM-DD}.md`

### Phase 6: QUALITY GATES (Haiku, grep-based)

For each drafted artefact (essay, thesis, deck outline):

1. **Factual audit** per `matchbox/workflows/factual-audit.md` — same 7 checks apply
2. **Voice lint** — em dashes, contractions, banned phrases, AI-tell signals
3. **Specificity check** — each draft must have at least 5 specific data points (numbers, named people, named companies, dates)

Any fail → reject the artefact, keep the report, log, continue.

### Phase 7: DIGEST

Write `digest.md`:

```
# Weekly Scan Programs - YYYY-MM-DD

## Summary
- Phase 1 Discover: N programs surveyed
- Phase 2 Filter: N survived
- Phase 3 Fetch: N details gathered
- Phase 4 Score: N scored (distribution)
- Phase 5 Draft: N artefact sets created
- Phase 6 Quality Gates: N passed

## New Programs with Open Windows
{Per program: name, deadline, score, fit signals, application artefact paths}

## Waitlist / Watch (not open yet, worth watching)
{Programs with future cohort dates to note}

## Closed / Rejected this Week
{Short list of programs checked and dismissed}

## Next Action for User
- Review N new artefact sets (essay + thesis + deck outline per program)
- Personalize beyond the generated draft (programs especially reward evident personal investment)
- For each submitted: say "submitted program {name}" to trigger apply workflow
```

## Multi-Application Hygiene

Same rule as jobs: if Shiva is applying to multiple programs simultaneously, do NOT cross-reference them in any essay. Each essay stands alone.

## Error Recovery

Same pattern as daily-jobs. Partial runs produce a PARTIAL digest.

## Known Limitations

- Program pages change formatting frequently; fetch success rate is 70-85%, not 95%+ like job APIs
- Application deadlines are often soft; a program "opens" weeks before the stated deadline
- Some programs require video submissions; this workflow does not generate video
- Some programs require references; manual user action required

## Success Criteria

Weekly run succeeds when:
1. Digest written, even if PARTIAL
2. 3+ programs were checked
3. Any program with "open" status has at least a scoring report (draft artefacts contingent on score)
4. User can act on the digest within 15 minutes of reading
