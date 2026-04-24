# Blind Spots — What We're Over- and Under-Engineering

**Date:** 2026-04-21
**Companion doc:** `cost-optimization.md` (which was about process efficiency within the current pipeline — this doc is about whether we're solving the right problem at all).

This is a meta-reflection on Matchbox. The other day we spent 10+ hours and $50-150 optimizing a pipeline we cannot yet evaluate (we have no outcome data). This doc names what we are building that we should not, and what we aren't building that we should.

---

## The biggest blind spot

**We are optimizing cost-per-tailored-CV. We should be optimizing interviews-per-dollar.**

- A $25 tailored CV that gets 0 responses costs infinity per interview.
- A $0 canonical CV that gets 1 response costs $0 per interview.
- A $200 interview-prep session that turns a screen call into an offer costs $200 per offer.

We have zero data on which of today's tailored CVs will get responses. Every "5x cost reduction" claim is theoretical because we don't know what correlates with outcomes. The content-as-JSON refactor in `cost-optimization.md` still assumes tailoring is the right investment. It might not be.

## Three sentences that matter

1. **Stop tailoring CVs industrially. Tailor cover letters for the few that matter; use a canonical CV for the rest.**
2. **Build outcome tracking. Every optimization without it is a guess.**
3. **Collapse Atma from 12 files to 4.** Halves every future agent's read cost permanently, at zero quality loss.

Everything else is polish on a system that already does the right things.

---

## Over-engineering we did

| What we built | Why it may be overkill | Honest replacement |
|---|---|---|
| 6-dimension scoring rubric | Most decisions reduce to "apply / review / skip". Users cherry-pick companies they recognize anyway. | 2 axes: `fit_for_you` + `red_flags`. Or ternary label. |
| `north_star` split into `company_mission_fit` + `role_mission_fit` | Barely shifted sort order (~5% of rows re-ranked) | Revert. One axis was enough. |
| 4 quality gates per CV | Gate 2 (page count) catches 90% of issues. Gates 1, 3, 4 are insurance the LLM is honest. | Keep gate 2 + gate 4 (voice grep is trivial). Drop gate 1 (template validation) and gate 3 (swap for a human spot-check on 2 sampled CVs per batch). |
| Atma has 12 identity files | `narrative.md` and `story-bank.md` overlap ~60%. `skills.md` is a subset of `cv.md`. `preferences.md` duplicates `profile.yml`. | Collapse to 4 files: `identity.yaml` (structured profile+skills+work), `stories.md` (narrative+story-bank combined), `voice.md` (rules only), `log.md` (auto-written). |
| 6-phase scan pipeline with 6 JSON checkpoints | Phases 1, 2, 3 often pass data through unchanged | 3 phases: discover → filter+score → persist. |
| 22 isolated tailor agents for 20 jobs | Zero context sharing, ~660K tokens of duplicated reads | One orchestrator, N content-dict outputs. |
| HTML template + base64 fonts + Chrome → PDF | Fragile. Fonts embedded 22 times. Chrome concurrency issues. | LaTeX or Typst (deterministic pagination, package-managed fonts, zero Chrome). Or pandoc from markdown. We ship PDFs, not HTML — we don't need the browser. |

## Under-engineering we did

| What we don't have | Consequence |
|---|---|
| **Outcome tracking** | Zero data on which applications got responses. Every optimization is theoretical. |
| **Follow-up system** | No 7-day-after-applying polite nudge. This is where responses actually come from for most people. |
| **Interview prep** | The workflow file exists but no implementation. Higher-value LLM use than CV tailoring. |
| **Recruiter CRM** | Recruiter name, company, contact preference, last message — no place for this. |
| **Warm-intro tracking** | 30-60% of real hires come via warm intro. Zero infrastructure. |
| **Re-tailor after master CV update** | When you improve `cv.md`, active tailored applications don't benefit. Lost improvement value. |
| **Per-application budget discipline** | Every application costs the same whether tier-1-dream or tier-3-lottery. |

---

## The mental model we are using is wrong

We built a **factory for industrial-scale CV tailoring**. What we need is a **surgical kit**:

- 3-5 deeply-researched applications per week (tier-1 dream roles)
- 5-10 templated applications per week (tier-2 target with standard tailoring)
- 10-20 cheap applications per week (canonical CV, generic cover, lottery tickets)

### Today's cost allocation is backwards

| Tier | Today's cost per app | Correct cost per app | Direction |
|---|---:|---:|---|
| Tier 1 dream (2-3 apps/week) | $1-2 | **$10-20** | UNDER-investing |
| Tier 2 target (5-10/week) | $1-2 | $1-2 | correct |
| Tier 3+ watchlist (rest) | $1-2 | **$0.05** | OVER-investing ~20x |

Net: same total budget. Each tier gets what it needs. Today we spread thin. Spread right instead.

---

## Non-obvious tricks

### 1. Canonical CV for 80% of applications
One master PDF, well-written once, used for tier-3 and lottery apps. Tailor only for tier-1 dreams and role-family outliers. **Saves 80% of today's tailor cost instantly.**

### 2. Tailor the cover letter, not the CV
Cover letters carry the narrative arc, the "why this role", the costly signals. CVs carry credentials (which don't change by company). A bespoke 150-word cover letter costs ~$0.20 and signals more than a 2-page CV rewrite. **Invert the effort allocation.**

### 3. Shrink the CV to the JD, don't expand it
Instead of inserting keywords the CV doesn't authentically have, DELETE bullets the JD doesn't care about. Subtractive is lower-risk than additive. You cannot fabricate what you delete.

### 4. Pre-computed "anchor packs" per role family
- FDE pack: 3 best stories, 5 best bullets, 1 opener, ranked
- SA pack: same structure, SA voice
- PM pack: same, PM voice

Tailor becomes "pick pack + specialize specifics". Fully deterministic, no rewriting, no voice risk. One-time 4-hour investment, reusable forever.

### 5. LLM as final reader, not author
Write the CV as yourself (or pick from templates). Ask Sonnet: "You are a recruiter at Anthropic. You have 15 seconds. What do you conclude? What's missing?" Iterate on **feedback**, not content generation. ~10x cheaper than rewriting.

### 6. Spec-test the CV before rendering
Declare what a good CV for a role MUST contain:
- Role title in first 100 words
- ≥ 3 named companies
- ≥ 2 falsifiable numbers
- 0 banned words
- Named stack keywords

Validate. If pass, render. If fail, report specifically what's missing. Forces agents to hit a contract cheaply.

### 7. Retrieval over generation
Maintain a corpus of the 10-15 best past CV versions. Tailor = "pick elements from which past CV to combine for this new one". Pattern-match beats creation. Cheaper AND more consistent voice.

### 8. Use the ATS's own parser to debug
If you can get a test account on Ashby/Greenhouse/Lever, you see what the system extracted from a submitted CV. Optimize for the extractor (5-10 keywords, structured sections), not the recruiter (who reads the extractor's summary).

### 9. Batch-identical JDs = identical CV
If 3 Deepgram SA roles share 90% of JD, produce ONE tailored CV and submit to all 3. Recruiters won't notice; ATS won't penalize. Multi-app hygiene is about cover letters, not CVs.

### 10. Skip cover letters for multi-app hygiene cases
When hygiene says "be silent about other applications," a generic-but-authentic cover letter performs as well as bespoke. Save bespoke for 1-2 apps per week that truly matter.

### 11. Measure what feeds back
Every response, rejection, interview, offer logged in `atma/people/shiva/wiki/log.md`. After 20-30 cycles, cluster: "Tier-1 FDE with bespoke cover gets 3x the response rate of Tier-2 SA with template." THAT is the real optimization signal.

### 12. LaTeX or Typst instead of HTML+Chrome
- Deterministic pagination (solves 3-page-CV problem forever)
- Package-managed fonts (zero base64 drama)
- Zero Chrome concurrency issues
- Reproducible by any contributor
- ~30-minute migration from current template

---

## The structural refactor (not a JSON change — a philosophy change)

Reframe from "tailor factory" to "application triage system":

```
incoming_job → tier classification → branch:
  if tier_1_dream:     deep_research + bespoke_tailor + custom_cover     ($10-20)
  if tier_2_target:    pack_based_tailor + template_cover                ($1-2)
  if tier_3_watchlist: canonical_cv + generic_cover                      ($0.05)
  if tier_4_explore:   canonical_cv + no_cover + auto_apply_if_possible  ($0.01)

after_apply → follow_up_schedule (d7, d14, d30) → response_logging
if_response → interview_prep_tooling → STAR+R story mapping from log.md
```

**Build around triage + follow-up + feedback.** Not around how cheaply we can tailor.

---

## Am I over-engineering this reflection?

Yes, a little. Three sentences suffice (repeated from top):

1. Stop tailoring CVs industrially. Tailor cover letters, not CVs, for most applications.
2. Build outcome tracking. Without it, every optimization is a guess.
3. Collapse Atma from 12 files to 4.

Everything else in this doc is supporting evidence.

## When to revisit

- After 20+ applications are submitted and have had 30+ days to receive responses: compare response rate by tier-vs-tailoring-depth. Re-evaluate whether tailoring was worth the cost on tier-2 and tier-3.
- Whenever pipeline cost exceeds budget in a given month: consult this doc before further optimization.
- **Review by:** 2026-07-21.
