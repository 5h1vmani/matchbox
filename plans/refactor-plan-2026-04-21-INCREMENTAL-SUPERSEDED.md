# Matchbox Refactor Plan — 2026-04-21

**Source documents:**
- `matchbox/docs/cost-optimization.md` — pipeline-level inefficiency analysis
- `matchbox/docs/blind-spots.md` — meta-level over/under-engineering analysis

**One-line goal:** reshape Matchbox from "industrial CV factory" into "application triage + outcome-feedback system" that is cheaper, more effective, and aligned with how real hiring decisions happen.

**Expected outcome after full implementation:**
- Tailor batch cost: ~$25-70 today → ~$3-8 after
- Time to produce 20-job batch: ~80 min → ~30 min
- Data loop closure: zero outcome signal today → full response-to-offer tracking
- Master CV edits propagate to active applications (today: they don't)
- Per-tier budget discipline replaces flat per-app spend

---

## Principles (decision filters for what to build)

1. **LLM for judgment. Code for transformation.** Every deterministic step is Python. LLM only for reasoning.
2. **Ship less, follow up more, measure outcomes.** Quality-of-submission + response-loop closure matters more than volume.
3. **Per-tier investment, not flat-rate.** Tier-1 dream gets 20x the care of a tier-4 lottery app.
4. **One source of truth per fact.** No "2 years vs 4 years" ambiguity across 15 briefs.
5. **Cheap before clever.** Ship canonical-CV + outcome-tracking before the LaTeX migration or content-as-JSON refactor.

---

## Phase 0 — Foundations (must precede everything)

### Step 0.1 — Collapse Atma from 12 files to 4
**Why:** every tailor agent reads 10-14 files today. Most overlap. This is the single biggest source of recurring read-cost across every future pipeline run.

**Current (12 files):** `profile.yml`, `cv.md`, `skills.md`, `projects.md`, `story-bank.md`, `voice.md`, `narrative.md`, `preferences.md`, `log.md`, `ai-detection-guide.md`, `routing.md`, `index.md`.

**Target (4 files):**
- `identity.yaml` — structured: candidate info + target_roles + title_filters + keywords + scoring weights + dream_tiers + exclusions + compensation + constraints + role_family_preference + work_history (with tagged bullets) + skills + projects (what was in cv.md + skills.md + projects.md + profile.yml combined into one SSOT)
- `stories.md` — narrative + story-bank merged (prose stories for cover letters and interview prep)
- `voice.md` — voice rules only (keep as is)
- `log.md` — auto-written activity log (keep as is)

Plus shared: `ai-detection-guide.md` stays in `atma/shared/`. `routing.md` + `index.md` collapse into one `atma/people/{profile}/index.md` (~30 lines).

**Effort:** 3-4 hours (careful conversion + fact verification).

**Success criteria:**
- `yaml.safe_load(identity.yaml)` parses.
- All facts that appeared in multiple old files now live in exactly one location in `identity.yaml`.
- NTT DATA tenure appears once, correct (2 years).
- Test: run one tailor through the new identity layer; output quality matches previous tailor.

### Step 0.2 — Outcome tracking columns in DB
**Why:** cannot optimize what we don't measure.

**Schema additions (via `_JOBS_REQUIRED_COLUMNS` in `db.py`):**
- `submission_date` (TEXT) — already exists as `applied_date`; keep but rename for clarity in new code
- `response_date` (TEXT)
- `response_type` (TEXT: `ghost` | `rejection` | `screen_scheduled` | `interview_invite` | `offer`)
- `response_note` (TEXT)
- `tailor_tier` (TEXT: `bespoke` | `template` | `canonical`)
- `tailor_cost_usd` (REAL)
- `tailor_cover_bespoke` (INTEGER) — 1 if cover was bespoke, 0 if template/none

**Effort:** 30 min.

**Success criteria:**
- Migration runs cleanly on live DB (146+ rows preserved).
- UI gets a "Log response" form on any `applied` row (4 fields: type, date, note, outcome).
- Can query: `SELECT tailor_tier, response_type, COUNT(*) FROM jobs GROUP BY 1, 2`.

### Step 0.3 — Canonical CV + canonical cover letter
**Why:** instant 80% cost reduction on tier-3 and tier-4 applications.

**Deliverable:**
- `atma/people/shiva/wiki/cv-canonical.md` — one master CV written as Shiva himself (no LLM). All voice rules satisfied, 2 pages, deliberately general-purpose but strong.
- `atma/people/shiva/wiki/cover-canonical.md` — one master cover letter, 3 paragraphs, no company-specific claims, strong opener about the builder-who-ships identity.
- Render once to `atma/shared/output/cv-canonical.pdf` and `cover-canonical.pdf`. Versioned in git.

**Effort:** 3-4 hours of user time (Shiva writes; Claude can help sharpen but not author).

**Success criteria:**
- Both PDFs pass the 4 quality gates.
- Human review confirms voice and factual accuracy.
- Tier-3 and tier-4 applications can use these verbatim.

---

## Phase 1 — Pipeline restructure (the philosophy change)

### Step 1.1 — Tier router
**Why:** every job gets different treatment based on tier. Route explicitly, not implicitly.

**New file:** `matchbox/shared/tier_router.py`.

**Inputs:** job dict (from DB).
**Output:** one of `bespoke` | `template` | `canonical` | `skip`.

**Logic:**
```
if job.dream_tier == "tier_1_dream" AND job.total_score >= 4.0:
    return "bespoke"
elif job.dream_tier in ("tier_2_target", "tier_3_watchlist") AND job.total_score >= 4.0:
    return "template"
elif job.total_score >= 3.5:
    return "canonical"
else:
    return "skip"
```

**Effort:** 30 min.

**Success criteria:**
- Unit tests for all 4 branches.
- UI shows tier-assignment per queued job.

### Step 1.2 — Per-tier tailor paths
**Why:** different tiers need different investment.

Three separate callable workflows/scripts:

**`tailor_bespoke.py`** (tier-1-dream, $10-20 per app)
- Deep research on company (recent news, product decisions, key people).
- Structured content generation using `identity.yaml`.
- Custom cover letter with company-specific anchor (mandatory).
- LLM-as-judge review pass.
- Human approval gate before marking tailored.

**`tailor_template.py`** (tier-2-target, $1-2 per app)
- Anchor-pack selection (FDE pack, SA pack, PM pack — one-time investment, see Step 2.2).
- Content generation: pick from pack + specialize minimally.
- Template cover letter with company name + opener variant.
- Quality gates (Python).
- No human gate.

**`tailor_canonical.py`** (tier-3/tier-4, ~$0.05 per app)
- No LLM call.
- Copy `cv-canonical.pdf` to output path with job-specific filename.
- Optionally attach `cover-canonical.pdf` if cover is required.
- Zero tailoring.

**Effort:** `tailor_canonical.py` = 30 min. `tailor_template.py` = 2 hours. `tailor_bespoke.py` = 3 hours (depends on Step 2.1).

**Success criteria:**
- Canonical tier: 1 run produces artefacts in < 5 seconds at $0 cost.
- Template tier: 1 run produces artefacts in 1-2 minutes at ~$1 cost.
- Bespoke tier: 1 run produces artefacts in 5-10 minutes at $10-20 cost, with human review step.

### Step 1.3 — Batch orchestrator replacement
**Why:** kill the 22-isolated-agents pattern. Single Python orchestrator calls the right path per job.

**New file:** `matchbox/shared/batch_tailor.py`.

**Pseudocode:**
```python
def run_tailor_batch(profile: str, queue: list[dict]) -> dict:
    results = []
    for job in queue:
        tier = tier_router.classify(job)
        if tier == "skip":
            continue
        if tier == "bespoke":
            artefact = tailor_bespoke.run(job, identity_yaml)
        elif tier == "template":
            artefact = tailor_template.run(job, identity_yaml, anchor_packs)
        elif tier == "canonical":
            artefact = tailor_canonical.run(job, canonical_cv, canonical_cover)
        gates.validate(artefact)
        db.mark_tailored(profile, job.id, cv_path=artefact.cv_pdf, cover_path=artefact.cover_pdf,
                         tailor_tier=tier, tailor_cost_usd=artefact.cost)
        results.append({"job_id": job.id, "tier": tier, "cost": artefact.cost})
    return summarize(results)
```

**Effort:** 2 hours.

**Success criteria:**
- Batch of 20 jobs completes in < 30 min.
- Total cost reported at end, matches per-tier expectations.
- Failed jobs stay in queue for retry; succeeded jobs marked `tailored` atomically.

---

## Phase 2 — Quality + voice infrastructure

### Step 2.1 — Pre-computed anchor packs
**Why:** eliminates runtime rewriting and voice risk. One-time investment, permanent reuse.

**Deliverable:** `atma/people/shiva/wiki/anchor-packs.yaml`:

```yaml
fde:
  opener_variants:
    - "In October 2025 I fired the development team three weeks in."
    - "Five months ago I had never shipped production code of my own."
    - "Most founders overcomplicate onboarding. The boring answer is..."
  bullets:
    - text: "Load-tested Pinaka to 250K concurrent users via K6 on ten parallel EC2 instances."
      tags: [scale, load-test, aws, production]
      voice_verified: true
    - text: "Shipped full AWS CDK stack — Lambda, DynamoDB, Step Functions, Cognito — in two months as a solo founder."
      tags: [aws, cdk, solo, shipping, founding]
      voice_verified: true
    # ... 8-12 total bullets per pack
  stories:
    - title: "Developer Graveyard (Oct 2025)"
      word_count: 180
      beats: [trigger, decision, proof, reflection]
      text: "..."
    # 3-5 stories

solutions_architect:
  # same structure, SA voice
product_manager:
  # same structure, PM voice
applied_ai_engineer:
  # same structure
```

**Effort:** 4-6 hours (Claude drafts; Shiva reviews and approves each variant).

**Success criteria:**
- All bullets pass voice lint (grep-based).
- Tagged bullets enable tag-based selection given JD keywords.
- `tailor_template.py` can produce a CV using only anchor-pack content + minimal company-specific line.

### Step 2.2 — Content-as-JSON + Python render
**Why:** stops paying LLM pricing for template substitution and HTML emission.

**Deliverable:**
- `matchbox/shared/tailor_content.py` — single Sonnet call: takes `(identity.yaml, anchor_packs, job, tier)`, returns `content_dict` (JSON conforming to schema).
- `matchbox/shared/render.py` — takes `(content_dict, template, fonts)`, produces `(html, pdf)`. Deterministic. Zero LLM.
- `matchbox/shared/gates.py` — takes `(html, pdf)`, runs 4 gates as Python functions, returns `{pass, violations}`. Zero LLM.

**Effort:** 4 hours.

**Success criteria:**
- One tailor produces a 2-page CV with zero voice violations end-to-end in < 90 seconds at < $0.30 cost.
- All 4 gates reliably catch known-bad inputs in test cases.
- Rendering is byte-identical given same inputs (deterministic).

### Step 2.3 — Migrate render to Typst (optional but recommended)
**Why:** deterministic pagination kills the "3-page CV" retry loop; no Chrome concurrency drama; package-managed fonts; reproducible.

**Effort:** 4-5 hours (learn + migrate template + verify output).

**Success criteria:**
- Produce visually-equivalent CV to current template.
- Rendering in < 500 ms (vs current Chrome ~2s).
- Pagination is content-length-deterministic (no retry loops).

**Tradeoff:** learning curve + one-time migration cost. Skip if current HTML+Chrome is "good enough."

---

## Phase 3 — Feedback loop (closes the learning cycle)

### Step 3.1 — UI response-logging form
**Why:** every response becomes a data point; without this, optimization is guessing.

**UI additions:**
- On any row in state `applied`: a "Log response" button expands a form with (type dropdown, date, note).
- Form writes to DB: `response_date`, `response_type`, `response_note`, and advances state (`applied → responded` for screen/interview; stays `applied` for `ghost`; `applied → rejected` for rejection; etc.).
- Weekly digest summarizes response rates by tier + cover-bespoke-or-not.

**Effort:** 1 hour.

**Success criteria:**
- Form appears and writes correctly.
- New rows appear in UI under appropriate states after 3 test responses logged.
- `SELECT tailor_tier, response_type, COUNT(*) FROM jobs WHERE response_date IS NOT NULL GROUP BY 1, 2` returns useful data after 20+ responses.

### Step 3.2 — Follow-up reminder
**Why:** responses come from follow-up, not from the original submission. This is where most hires actually originate.

**Implementation:**
- Every row entering `applied` state gets a calendar reminder (stored as `follow_up_date = applied_date + 7 days`).
- Daily scan workflow checks for rows with `follow_up_date <= today AND response_date IS NULL AND state = 'applied'`.
- Surface a "Follow up due" section in the UI.
- Optional: generate a polite follow-up email draft via Haiku when user clicks "Draft follow-up."

**Effort:** 2 hours.

**Success criteria:**
- Follow-up reminders surface correctly 7 days after application.
- User can mark follow-up as sent; next reminder is 14 days later.
- After 30 days with no response, auto-mark as `ghost`.

### Step 3.3 — Outcome analytics
**Why:** makes the feedback loop visible; enables evidence-based optimization decisions.

**Implementation:**
- New UI tab or section: "Outcomes".
- Shows:
  - Response rate overall, by tier, by role family, by country, by cover-type.
  - Median days to first response.
  - Which anchor-pack bullets correlate with more responses (after 30+ data points).
- Export as CSV for offline analysis.

**Effort:** 2-3 hours.

**Success criteria:**
- After 20+ logged outcomes, the table shows statistically meaningful differences (or lack thereof).
- Data drives the next refactor priority.

---

## Phase 4 — Rubric + scan simplification (optional pruning)

Revisit after Phase 3 is producing outcome data.

### Step 4.1 — Collapse 6-dim rubric to 2 dims
**Why:** if response data shows the rubric's finer dimensions don't correlate with outcomes, simplify.

**New rubric:** `fit_for_you` (0-5) + `red_flags` (0-5). Total = weighted avg.

**Effort:** 2 hours (including re-scoring active rows).

**Precondition:** outcome data from Phase 3 shows no correlation between individual old dimensions and response rate.

### Step 4.2 — Collapse 6-phase scan to 3
**Why:** phases 1, 2, 3 currently pass data through with minor changes. Merge them.

**New pipeline:** `discover → filter_score → persist`.

**Effort:** 3 hours.

**Precondition:** nothing blocking; can do any time after Phase 1.

---

## Dependency graph

```
0.1 Atma 12→4          0.2 DB columns       0.3 Canonical CV
     ↓                      ↓                     ↓
    1.1 Tier router ────────┴───────────────────┘
     ↓
    1.2 Tier-specific tailor paths
     ↓
    1.3 Batch orchestrator
     ↓
    ... (parallel with) 2.1, 2.2, 2.3
     ↓
    3.1 UI response form
     ↓
    3.2 Follow-up reminders
     ↓
    3.3 Outcome analytics
     ↓
    4.1 Rubric simplification (if data supports)
    4.2 Scan pipeline simplification
```

---

## Priority order (what to build first)

Ranked by **leverage (ROI per hour of effort)**:

1. **Step 0.2 — DB columns** (30 min, unblocks all outcome tracking). Do first.
2. **Step 0.3 — Canonical CV** (3-4 hours of Shiva's time). Saves 80% of cost on tier-3/4 apps starting immediately.
3. **Step 3.1 — UI response form** (1 hour). Start collecting outcomes before spending any more on tailoring optimization.
4. **Step 0.1 — Atma collapse** (3-4 hours). Foundation for every future agent read.
5. **Step 1.1 + 1.2 + 1.3 — Tier router + per-tier paths + batch orchestrator** (5-6 hours). The core of the philosophy change.
6. **Step 3.2 — Follow-up reminders** (2 hours). Where real hires come from.
7. **Step 2.2 — Content-as-JSON** (4 hours). The cost refactor.
8. **Step 2.1 — Anchor packs** (4-6 hours of Shiva's time). Quality floor for tier-2 tailoring.
9. **Step 3.3 — Outcome analytics** (2-3 hours). After 20+ data points.
10. **Step 2.3 — Typst migration** (4-5 hours). Nice-to-have; skip if current pipeline is stable.
11. **Step 4.1 + 4.2 — Rubric + scan simplification** (5 hours). Only after outcome data supports the case.

**Total effort across all phases:** ~35-45 hours.
**Minimum viable refactor (steps 0.1 through 3.2):** ~20 hours. Delivers the philosophy change + outcome loop.

---

## Success metrics (measure these at each phase end)

| Metric | Today | After Phase 0 | After Phase 1 | After Phase 3 |
|---|---:|---:|---:|---:|
| Cost per 20-job batch | $25-70 | $15-40 | $3-8 | $3-8 + data |
| Time per 20-job batch | 80 min | 60 min | 30 min | 30 min |
| Outcome data points | 0 | 0 | 0 | 20+ |
| Shared fact errors (e.g. NTT DATA years) | occasional | 0 (single source) | 0 | 0 |
| Tier-1 dream apps per week | 0-1 | 2-3 (with canonical fallback for others) | 2-3 | 2-3 |
| Canonical-CV apps per week | 0 | 10-15 | 10-15 | 10-15 |

---

## What this plan does NOT try to do

- **Rebuild the scan discovery** — current pipeline is ~$0.06 per weekly sweep, already efficient.
- **Migrate off Streamlit** — UI is functional; polish later when open-sourcing.
- **Replace the DB** — SQLite SSOT is the right call.
- **Build a recruiter CRM** — deferred until there are recruiter relationships to track.
- **Build warm-intro tracking** — requires human workflow design, not code.

These are all legitimate future work, but not in this refactor.

---

## Review checkpoints

- **After Step 0.3 (Canonical CV):** ask if the quality of canonical CV is acceptable for 80% of applications. If not, adjust.
- **After Phase 1 complete:** run one 20-job tailor batch. Compare cost + time + output quality to today's batch. If not significantly better, revisit the architecture.
- **After 20 outcomes logged (Phase 3.3):** review response rates by tier. If tier-3 canonical apps get similar response rates to tier-2 templated, consolidate. If bespoke apps don't meaningfully outperform templated, collapse those too.
- **Review by:** 2026-07-21.

---

## Notes to the builder (Claude or human)

- Do not build Step 2.3 (Typst) without explicit user approval — cosmetic migration.
- Do not collapse the rubric (Step 4.1) without Phase 3 data showing dimensions don't correlate.
- Do verify in the first hour of Step 0.1 that the new `identity.yaml` structure round-trips cleanly through an existing tailor workflow. Abort and refactor if not.
- Keep `matchbox/docs/blind-spots.md` open during implementation — the 3 sentences at the top are the decision filter.
