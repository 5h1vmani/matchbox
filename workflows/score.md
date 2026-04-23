---
id: score-workflow
purpose: How to score a single JD against the profile and write the evaluation report
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 2500_tokens
---

# Score Workflow

Score a single job description against the user's profile and write a one-page evaluation report. Invoked from `scan.md` phase 4, but can also run standalone (user pastes a JD).

## Ashby LLM-Summary Rule (added 2026-04-20)

Modern ATS (Ashby, Lever, Greenhouse v2) generate LLM summaries from the candidate's materials. The recruiter sees this summary BEFORE the full document. When scoring a JD, the report's "Tailoring Notes" section must specifically call out:

- Which 5-7 keywords from the JD need to appear in the CV's first 500 words
- Which specific bullets from the candidate's work experience must lead in the first 1-2 roles of the tailored CV
- Which opening sentence structure (for cover letter) would rank highest given the JD's language

**This is not generic ATS optimization. It is specific to the summary-generation mechanism.** The tailor workflow reads these notes and optimizes the first-500/first-150 window accordingly.

## Pre-requisites

- JD text available (from scan phase 3 or pasted by user)
- Atma routing permits the `job_scoring` task for the target user
- `atma/shared/scoring-rubric.md` loaded

## Read Set (Atma Routing: job_scoring)

From `atma/people/{name}/routing.md`:
```
always:    [profile.yml, skills.md]
sometimes: [preferences.md, log.md#last-30d, projects.md]
never:     [comp.md, network.md, traction.md, writing-samples/*]
budget:    8000_tokens
```

Matchbox does not read beyond this set. Deny wins on `never` entries.

## Procedure

### Step 1: Legitimacy Check (pre-scoring gate)

Before spending tokens on dimension scoring, verify the posting is real.

Run the signal table from `atma/shared/scoring-rubric.md`. Flag with one of:

- `legitimacy: high`, fresh, specific, apply button active, realistic requirements
- `legitimacy: caution`, mixed signals; proceed but note in report
- `legitimacy: ghost`, >60 days old OR apply button dead OR copy-paste generic; **stop scoring**, log as skipped, move on

Ghost postings do not get scored. They get a minimal entry in `applications.md` with status `skip` and note "ghost posting: {reason}".

### Step 2a: Sector Exclusion Gate (added 2026-04-21)

Before scoring, check `profile.yml:exclusions` against the role's sector and country.

- Determine the sector from the JD (defense, crypto, gambling, fossil_fuels, alcohol, tobacco, or "none").
- For each excluded sector, read `global_default`; then check `overrides.{country}` if present.
- If the effective decision is `exclude`:
  - Set `red_flags_score = 0.5`
  - Set `recommendation = SKIP`
  - Stamp `exclusion_triggered = "{sector}|{country}"` into the DB row via `db.update_job`
  - Skip dimensions 1-5; jump to Step 4 (report) with the exclusion reason noted
  - Example: a Palantir defense role in the US → excluded. A BEL AI defense role in India → scored normally because of override.

### Step 2b: Score Each Dimension (1-5, six dimensions)

Apply `atma/shared/scoring-rubric.md` dimensions:

1. **CV Match** — does candidate's experience align with role requirements?
2. **Company Mission Fit** — does working at THIS COMPANY advance candidate's mission? Read `profile.yml:dream_tiers`. tier_1 baseline 5.0, tier_2 baseline 4.0, tier_3 baseline 3.0, tier_4_exploratory baseline 2.5, not-in-any-tier default 3.0. Adjust from baseline based on recent company news, leadership quality, trajectory.
3. **Role Mission Fit** — does THIS ROLE do mission-aligned work? Score the role's responsibilities, not the company. A PMM at Anthropic might score 2 here even while company_mission_fit = 5.
4. **Compensation** — is stated pay at or above `profile.yml:compensation` minimum for the role's geography?
5. **Cultural Signals** — remote/growth/team quality/stability match `preferences.md`?
6. **Red Flags** — layoff news, reposting pattern, other concerns.

For each dimension, cite specific JD text or profile fact as evidence. No unsourced claims.

### Step 2c: Role Family Classification (added 2026-04-21)

Classify the role into one of the families used by `profile.yml:role_family_preference`. Match substrings against the role title:

- `solutions_architect_startups` — "Solutions Architect" + ("startup" OR "early" OR "pre-seed" OR "Series A")
- `solutions_architect_general` — "Solutions Architect" OR "Solutions Engineer" (no startup qualifier)
- `applied_ai_engineer` — "Applied AI" OR "Applied Machine Learning" OR "Deployment Engineer"
- `forward_deployed_engineer` — "Forward Deployed" OR "FDE"
- `ai_product_lead` — "AI Product Lead" OR "Head of AI Product" OR "Principal PM" + AI
- `product_manager_ai` — "Product Manager" + ("AI" OR "ML" OR "GenAI")
- `founding_engineer` — "Founding Engineer" OR "Founding AI Engineer"
- `devrel_ai` — "Developer Relations" OR "DevRel" OR "Developer Advocate"
- `consultant_ai` — "AI Consultant" OR "ML Consultant"

Write the matched family key to `db.jobs.role_family`. If no family matches, leave it NULL. The UI uses this for within-company sort order.

### Step 3: Apply Weights

Read `profile.yml:scoring` weights. Multiply each dimension score by its weight, sum.

```
total_score = cv_match × w_cv
            + company_mission_fit × w_cmf
            + role_mission_fit × w_rmf
            + compensation × w_comp
            + cultural × w_cult
            + red_flags × w_rf
```

**Sanity check:** weights must sum to 1.0. If the profile has weights that do not sum to 1.0, flag the file for lint.

**Legacy rows:** rows scored before 2026-04-21 used a 5-dim rubric with `north_star_score`. To preserve them, fall back to `north_star_score` if the two new columns are NULL when displaying. New rows always populate `company_mission_fit_score` and `role_mission_fit_score`.

Final score rounds to one decimal place.

### Step 3a: Persist all sub-scores to DB

Call `db.update_job(profile, job_id, ...)` or `db.insert_job(...)` with every sub-score populated:

- `cv_match_score`
- `company_mission_fit_score` (new)
- `role_mission_fit_score` (new)
- `comp_score`
- `cultural_score`
- `red_flags_score`
- `total_score`
- `recommendation`
- `role_family` (from Step 2c)
- `dream_tier` (tier_1_dream | tier_2_target | tier_3_watchlist | tier_4_exploratory | NULL)
- `exclusion_triggered` (if sector gate fired in Step 2a)

Leave `north_star_score` NULL for new rows. It is the legacy column, not a computed alias.

### Step 4: Write the Report

**Path:** `people/{name}/reports/{NNN}-{company-slug}-{YYYY-MM-DD}.md`

**Numbering:** `{NNN}` is a 3-digit zero-padded sequential number per user. Read the highest number in `applications.md`, increment.

**Slug:** lowercase, hyphen-separated, strip special characters.

**Template:**

```markdown
---
id: report-{NNN}
purpose: Evaluation report for {company} - {role}
sensitivity: private
relevant_for: [job_scoring, interview_prep]
not_for: [social_post, essay_draft]
last_updated: {YYYY-MM-DD}
review_by: {YYYY-MM-DD + 30 days}
size_budget: 1500_tokens
---

# {Company} - {Role}

**Date:** {YYYY-MM-DD}
**URL:** {posting URL}
**Geography:** {inferred location / remote status}
**Legitimacy:** {high | caution | ghost}
**Score:** {X.X}/5
**Recommendation:** {APPLY | REVIEW | SKIP}

## Dimension Scores

| Dimension | Score | Weight | Contribution | Evidence |
|-----------|-------|--------|--------------|----------|
| CV Match | {N} | {W} | {N×W} | {specific match or gap} |
| Company Mission Fit | {N} | {W} | {N×W} | {tier baseline + adjustments} |
| Role Mission Fit | {N} | {W} | {N×W} | {role-level day-to-day fit} |
| Compensation | {N} | {W} | {N×W} | {stated pay vs minimum} |
| Cultural | {N} | {W} | {N×W} | {remote, stage, team clues} |
| Red Flags | {N} | {W} | {N×W} | {concerns or exclusions} |
| **Total** | - | 1.00 | **{X.X}** | - |

**Role family:** {matched family or "unclassified"}
**Dream tier:** {tier_1_dream | tier_2_target | tier_3_watchlist | tier_4_exploratory | none}
**Exclusion triggered:** {none | sector|country, e.g. "defense|us"}

## Match with CV

| JD Requirement | Candidate Evidence | Gap? |
|----------------|--------------------|------|
| ... | ... | ... |

## Key Strengths for this Role
- ...
- ...

## Gaps or Risks
- ...
- ...

## Legitimacy Signals

| Signal | Finding |
|--------|---------|
| Posting age | ... |
| Apply button | ... |
| JD specificity | ... |
| Requirements realism | ... |
| Company layoff news | ... |
| Reposting pattern | ... |

## Recommendation

{APPLY | REVIEW | SKIP}: {one-sentence reason}

**If APPLY:** Tailor CV. Apply within 7 days of posting to maximize freshness signal. See `output/cv-{company-slug}-{YYYY-MM-DD}.pdf` once tailored.

**If REVIEW:** Specific question(s) for user to answer before deciding.

**If SKIP:** Reason logged for pattern analysis (see `atma/people/{name}/wiki/log.md` lint findings).

## Keywords Extracted

{15-20 keywords for ATS; used in CV tailoring phase}

## Tailoring Notes

Instructions specific to this JD for the tailor phase:
- Opening line emphasis: {...}
- Top bullets to reorder first: {...}
- Competency section focus: {...}
- Projects to feature: {...}
```

### Step 5: Update `applications.md`

Append a row to the pipeline tracker. Use the state machine from `shared/states.yml`:
- `evaluated`, report written, awaiting human decision
- `skip`, auto-skipped (score < 3.5 OR ghost posting)

Row format (tab-separated, see `applications.md` template):
```
{NNN} | {date} | {company} | {role} | {score}/5 | {state} | {pdf_emoji} | [{NNN}](reports/{NNN}-{slug}-{date}.md) | {one-sentence note}
```

### Step 6: Trigger Tailor (conditional)

If `score >= mode.yml:thresholds.tailor_min`, invoke `tailor.md` workflow for this JD.

## Cost Budget

- Reading Atma (routing-limited): ~5K tokens
- Reading JD: ~500-2K tokens
- Reasoning + report: ~2K tokens
- Writing report: ~1K tokens

**Total per scored JD: ~8-10K tokens**

If budget exceeded, the issue is usually JD bloat, trim the JD to its substantive body before passing to the scorer.

## Failure Modes

- **All dimensions score similarly**: the scorer is applying a global feeling, not the rubric. Force it to cite specific evidence per dimension.
- **Compensation dimension always 3**: the JD has no comp info. Either accept the ambiguity (score 3) or note "comp undisclosed" in the report and move on.
- **Cultural score depends entirely on stock phrases** ("we're a team of passionate people"), cultural dimension relies on concrete facts, not adjectives. Score 3 (ambiguous) when no concrete signal exists.
