---
id: scan-workflow
purpose: The 5-phase funnel for discovering, deduplicating, fetching, scoring, and tailoring job opportunities
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 3000_tokens
---

# Scan Workflow

The scan is a funnel. Each phase is cheaper than the next. Most jobs drop out early so we spend the least on the most opportunities and the most on the fewest.

## Phases

### Phase 1: DISCOVER

**Source:** `people/{name}/search-queries.yml`
**Action:** Execute the listed web search queries. Collect results as `{title, company, location, url, snippet}`.
**Cost:** ~100 tokens per query.

**Rule:** do not visit job boards directly. Search the web. One search returns LinkedIn, Greenhouse, Lever, Ashby, company pages in one call. A search snippet is enough to dedup and filter without fetching full pages.

**Exception:** for `dream_companies` listed in `profile.yml`, call the structured API if available (Greenhouse `boards-api.greenhouse.io/v1/boards/{slug}/jobs`, Ashby equivalent). JSON is cheaper than HTML search.

### Phase 2: DEDUP + TITLE FILTER + GEO FILTER

**Action:**
1. **Dedup key:** normalize `company + title + location` (lowercase, strip seniority prefix, strip trailing markers like "LLC" / "Pvt Ltd").
2. Check the key against `people/{name}/applications.md`, if present, skip.
3. Apply title filters from `atma/people/{name}/wiki/profile.yml`:
   - Positive match required (at least one keyword from `title_filters.positive`)
   - Negative match forbids (any keyword from `title_filters.negative` drops it)
   - Seniority keywords from `title_filters.seniority_boost` increase a hit's priority, not its eligibility
4. **GEO FILTER (added 2026-04-20):** apply `atma/people/{name}/wiki/profile.yml:geography_policy`:
   - Read `dream_companies` list from profile.yml.
   - If company is in `dream_companies`:
     - Any location passes. On-site US/UK/EU roles are acceptable IF visa sponsorship is likely; flag `needs_visa_check` for Phase 4 legitimacy review.
   - Else (non-dream company):
     - Must be India-based OR remote-eligible for candidates in India.
     - Drop roles that require relocation outside India.
   - If the JD has no clear location field, flag `geo_unknown` and let Phase 4 determine from fetched JD.
5. Apply `deal_breakers` from profile.yml as final override. Any match drops the role regardless.

**Cost:** zero extra tokens (string operations on data already in memory).

**Output:** shortlist of ~20-40% of phase 1 results.

**Pilot learning (2026-04-20):** before the geo filter existed, 7 of 8 scored roles failed because of relocation blockers that could have been caught here. This filter is the biggest single token saver in the funnel.

### Phase 3: FETCH

**Action:** retrieve the full JD only for shortlisted survivors.

**Preferred sources (cheapest first):**
1. Greenhouse/Ashby/Lever JSON API, clean structured data (~200 tokens per JD)
2. Company ATS page, if URL points directly to one
3. Web fetch with extraction prompt, last resort (~500-800 tokens)

**Extract only:**
- Job description body (role, responsibilities, requirements, qualifications)
- Compensation if stated
- Location / remote policy
- Posting date (for legitimacy check)

**Ignore:** ads, related jobs, "about us" boilerplate, footer, nav.

**Cost:** ~200-500 tokens per survivor.

### Phase 4: SCORE

**Action:** apply `atma/shared/scoring-rubric.md` to each fetched JD.

**Declare task:** `job_scoring`
**Atma routing returns:** `profile.yml` (always), `skills.md` (always), plus `preferences.md` / `log.md#last-30d` / `projects.md` (sometimes, only if needed).

**Legitimacy check runs first** (pre-scoring gate):
- Posting age > 60 days? Flag `ghost`, do not score.
- Apply button dead or JD looks copy-paste generic? Flag `suspicious`, score with caution.
- Named red flags (see `atma/shared/scoring-rubric.md` legitimacy table)? Flag and note.

**Apply rubric:** score each of the 5 dimensions 1-5, weighted by `profile.yml:scoring` weights, sum to the final score.

**Output:** one-page report per scored JD, written to `people/{name}/reports/{NNN}-{company-slug}-{YYYY-MM-DD}.md`.

**Cost:** ~1K tokens per scored JD.

### Phase 5: TAILOR

**Triggered for:** score ≥ `mode.yml:thresholds.tailor_min`.

**Declare task:** `cv_tailoring`
**Atma routing returns:** `cv.md` (always), `skills.md` (always), `projects.md` (always), `story-bank.md` / `voice.md` / `narrative.md` (sometimes).

**Action:**
1. Extract 15-20 keywords from JD.
2. Reformulate existing bullets in `cv.md` to use JD vocabulary. **Never invent skills or claims.**
3. Reorder bullets by JD relevance.
4. Rewrite Professional Summary with top 5 JD keywords.
5. Select top 3-4 most relevant projects.
6. Apply `atma/shared/ai-detection-guide.md` checklist.
7. Apply `atma/people/{name}/wiki/voice.md` rules (no em dashes, no contractions, no banned phrases).
8. Render via `atma/shared/cv-template.html` → produce HTML → PDF.

**Output:** `people/{name}/output/cv-{company-slug}-{YYYY-MM-DD}.pdf` plus `.html` source.

**Cost:** ~3K tokens per tailored CV.

## Token Budget Example (Warm Mode, 100 discovered hits)

| Phase | Jobs in | Cost/job | Total |
|-------|---------|----------|-------|
| 1. Discover | 100 | 100 | ~3K (30 queries × 100) |
| 2. Dedup + filter | 30 survive | 0 | 0 |
| 3. Fetch | 30 | 400 avg | 12K |
| 4. Score | 30 | 1K | 30K |
| 5. Tailor (≥3.5 threshold) | ~10 | 3K | 30K |
| **Total** | - |, | **~75K tokens** |

Without the funnel: ~450K for the same 100 hits. 6x savings.

## Scan Output (What the User Sees)

At the end of a scan, Matchbox returns a digest:

```
SCAN COMPLETE, 2026-04-19
  Queries run: 12
  Discovered: 94 unique hits
  Passed filters: 28
  Scored: 28 (legitimacy: 25 OK, 2 ghost, 1 caution)
  Score ≥ 4.0 (tailored): 7
  Score ≥ 4.5 (surfaced): 2
  
SURFACED:
  - Anthropic, Forward Deployed Engineer (India/Remote), 4.6/5
    report: reports/012-anthropic-2026-04-19.md
    tailored: output/cv-anthropic-2026-04-19.pdf
    
  - Perplexity, Senior AI Product Manager (Remote), 4.5/5
    report: reports/013-perplexity-2026-04-19.md
    tailored: output/cv-perplexity-2026-04-19.pdf

BELOW SURFACE (tailored, awaiting review):
  - Sarvam AI, Product Lead, 4.2/5
  - Modal Labs, Developer Experience Engineer, 4.1/5
  - 3 more (see applications.md)

AUTO-SKIP (< 3.5): 18
GHOSTED: 2

Next action: review the 2 surfaced. Full pipeline in applications.md.
```

The user reviews, decides which to apply to, and triggers `apply.md` workflow.

## Failure Modes

- **Query list too broad**: returns too many irrelevant hits, wastes tokens in phases 3-4. Fix: tighten `search-queries.yml` positive terms.
- **Query list too narrow**: misses real opportunities. Fix: add adjacent role titles or dream companies.
- **Title filter too aggressive**: good jobs get dropped at phase 2. Fix: loosen negative filters; check phase 2 output.
- **All scores low**: rubric weights misaligned with reality. Fix: tune `profile.yml:scoring` weights.
- **All scores high**: rubric weights too generous, or filters let everything through. Fix: examine a specific report manually; often the rubric is being applied loosely.

## What's Not in v1

- Scheduled execution (cron), manual trigger for now
- Incremental scanning (only new postings since last run), add when runs per day > 1
- `scan-history.tsv` audit log, add when debugging query set changes
- Auto-apply, never in any version; submission is always human
