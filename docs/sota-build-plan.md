# SOTA Matchbox — build plan

Status: active. Scope decided 2026-06-05: **the job ends at "offer accepted."**
This plan governs sequencing for the backend rebuild. Product priorities still
live in `product-thesis.md`; where this disagrees on *sequencing*, this wins.

## The arc (the job, end to end)

```
Set up → Find → Judge → Apply → Track → Advance → Close → (Learn, cross-cutting)
```

Each phase has a SOTA bar and a "doable" verdict (see the strategy memo in the
session). The through-line: **the agent proposes, the deterministic core
disposes.** The LLM is the user's swappable agent; every guarantee
(truthfulness, voice, selection, scoring) lives in Python and never depends on
which model runs. The LLM never runs per-job across the pool — only once per
*pursued* job.

## Architecture principles (non-negotiable)

1. **Truthful by construction.** Only verified facts reach any artifact (CV,
   cover, prep brief, follow-up, counter-offer). Gaps are reported, never filled.
2. **No LLM per job at pool scale.** Pool enrichment is API + deterministic
   regex. The agent parses a JD only after the user marks it.
3. **One fact model.** Today there are two (`bullet`, live; `claim/rendering`,
   dormant). Converge on `claim` (it carries STAR + evidence + defensibility —
   exactly what interview-prep and honest-gap framing need) during Phase 0.
4. **The DB is the contract.** The dashboard writes intents to `agent_task`; the
   agent drains them and writes results back. No human as the message bus.
5. **Local-first, multi-user.** One SQLite DB per person under `people/<slug>`.
   Nothing leaves the device.

## Phases

### Phase 0 — Foundation (data model + lean-up)  ← IN PROGRESS
- [x] Migration 007 (additive): enrich `job` (salary, employment_type,
      seniority, min_years_exp, role_family, eligibility signals, remote_scope,
      dedup_key, company_id); new `company`, `requirement`, `artifact`, `offer`,
      `agent_task`; `application` += predicted-fit snapshot; `voice_profile`;
      `target` work-auth block. Backfill `company` + `dedup_key` from existing rows.
- [ ] Verified lean-up (separate, after tracing readers): pick the live PDF
      renderer and delete the other; drop legacy `application.status`/`notes`
      once `create_application` stops writing `status`.
- [ ] `AGENTS.md` — vendor-neutral instruction file; `CLAUDE.md` becomes a thin
      pointer to it.

### Phase 1 — Find (enrichment)
- [ ] Tier-1: persist salary/employment_type/category/etc. from source APIs
      (Adzuna especially — currently discarded).
- [ ] Tier-2: deterministic local pass at scoring time — eligibility regex
      (sponsorship/citizenship/clearance/remote-scope), seniority-from-title,
      `dedup_key`, `company` link.
- [ ] Paste-a-JD as a first-class add path (agent parses one JD → `job` +
      `requirement`).

### Phase 2 — Judge (eligibility at scale)
- [ ] Deterministic eligibility pre-filter: job signals vs `target` work-auth.
- [ ] Promote requirements into the `requirement` table; coverage becomes a
      real query. Surface eligibility + coverage in the discovery serializer.

### Phase 3 — Apply (trust surface + artifacts)
- [ ] Tailored CV/cover → `artifact` rows; expose the "what changed + gaps"
      diff (already computed in `changes.md`/`coverage.json`) via the API.
- [ ] Snapshot `predicted_band`/`predicted_score` on the application at create.

### Phase 4 — Advance (prep + drafts)  *new scope*
- [ ] Agent jobs: interview-prep brief (STAR from `claim` + JD + stage),
      follow-up/thank-you drafts → `artifact` rows (voice-bounded).
- [ ] Every stage change writes an `app_event` (the funnel substrate).

### Phase 5 — Close (offer)  *new scope*
- [ ] `offer` model; comparison on the user's weights; benchmark from the
      user's own discovered-role salary ranges (confidence-labelled).
- [ ] Negotiation-counter draft (agent job, voice-bounded). `accepted` stage.

### Phase 6 — Learn (cross-cutting; the thesis's #1 gap)
- [ ] Outcome capture (terminal states + dates via `app_event`).
- [ ] Calibration: predicted band vs actual conversion; funnel; what's working.
      Measure and report only — never auto-retune ranking (permanent non-goal).

### Cross-cutting — the agent loop
- [ ] `agent_task` queue + a drain protocol section in `AGENTS.md`. Replaces the
      `runs/<id>/work-queue.json` copy-paste hand-off.

### UI (after the design team delivers the 7 screens)
- [ ] Build in React in the unified Shell; retire each Jinja page as its React
      replacement lands. Screens: Intake/completeness, Search/sources,
      Tailoring-review/apply, Application workspace (prep+drafts), Offer,
      Insights, Library.

## Verification discipline

Code and real data are ground truth; distrust docs and reports until verified
against code. Every backend phase ships with tests and a green suite before the
next begins.
