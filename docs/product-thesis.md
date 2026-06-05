# Matchbox — product thesis (north star)

Status: locked 2026-05-29. This document governs **priorities**. Where it
disagrees with the sequencing in `v0.4-design.md`, this wins. Technical
detail still lives in `v0.4-design.md`; the data-science rationale in the
session that produced this.

## What Matchbox is

> A local-first tool that gets an average person **more interviews with
> near-zero effort**: it finds the right roles from many sources, judges
> fit **honestly**, and assembles **truthful, keyword-aligned**
> applications from a reusable sentence pool — calling an LLM rarely, and
> **never per job**. The user's data never leaves their machine.

End goal: a job that fits the user's goals. Not more applications. More
*right* applications, with less effort.

## Locked decisions (this session)

- **Generic, not personal.** Will be open-sourced.
- **Engine first on the current CLI + agent model.** Build and prove the
  backend on what we have. Package a one-click **desktop app with a
  BYO-API-key** screen for non-technical users **only once the engine is
  proven and consistent.** "Average user" is a packaging phase, not a
  constraint on the engine.
- **India first**, then global-remote, then EU, then US. But the data
  model is **country-agnostic**: every job carries a `country` and a
  `remote` flag, and the user filters ("Remote — India", "On-site
  Bangalore", "Remote — US"). Only the source integrations are sequenced.
- **Full-time roles first.** Freelance/gig later.
- **Local-first, BYO-intelligence.** The app holds no model and no key by
  default. The LLM is the user's agent now; their pasted API key later.

## Target user

An average person with minimal technical understanding (friends, family,
students, interns). Today they need a developer to run it; that is
acceptable **during engine development only**. The desktop packaging
closes that gap before we call it done.

## The five pillars (priority order)

1. **Find** — many sources + a universal paste-a-link path, with curated
   seeds so it works on day one without the user naming companies.
2. **Judge fit honestly** — semantic + calibrated scoring (built). Says
   "skip this, you are a 3/10" and "prioritize this, you are a 9/10."
   This is what saves the user's scarcest resource: time.
3. **Apply with near-zero effort** — the reuse-CV model below.
4. **Honest by construction** — only verified facts reach a document;
   gaps are reported, never papered over.
5. **Learn** — track applied -> interview -> offer, calibrate, and tell
   the user what is working. Today we measure nothing; this is the gap
   that proves whether any of it works.

## The reuse-CV model (core design principle)

The expensive, naive design calls an LLM to draft a CV per job. Two
backend-engineer CVs are ~90% identical, so that is mostly wasted spend.
Instead:

- **Draft a stable pool of truthful sentences once** (at onboarding, and
  incrementally as the user adds history). Each fact is a `claim`; each
  claim has one or more pre-drafted **phrasings** (`rendering` rows) —
  e.g. one leading with "AWS", one with "infrastructure as code", one
  tighter for space. This is the `claim -> rendering` graph already in the
  schema (migration 002); the reuse model is the use case it was built
  for.
- **Per job: no LLM.** An algorithm selects the matching phrasings and
  aligns keywords. Cost per job is fractions of a cent.
- **Truth-constrained keyword alignment.** Safe synonym swaps only
  (`k8s` = `kubernetes`, `postgres` = `postgresql`). A different cloud is
  **not** a synonym: if a JD wants Azure and the user has only AWS, that
  is a reported **gap**, never an injected keyword. The user's verified
  facts are the truth boundary.
- **LLM only on a genuine gap** — when a verified fact truly matches a JD
  term but no phrasing carries it, call the LLM **once** to draft a new
  truthful phrasing, which then joins the pool forever.

Net LLM usage: onboarding (parse files), occasional gap-fill, never the
per-job loop.

## Discovery architecture

A pluggable `source` layer. Every job normalized to: company, title,
`country`, `remote`, location, url, jd_text. Sources, verified
2026-05-29:

**Integrate first (clean ToS):**
- **ATS pollers** (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee)
  — public, no auth, built. India *tech/startup* + global. The spine.
  Add **curated company seed lists** so it returns jobs without the user
  naming companies.
- **Himalayas** — public no-auth remote board; terms explicitly permit
  powering search experiences and AI agents; has an India filter. Best
  terms of the remote group. Honor attribution + rate limits.
- **Adzuna** — free **BYO-key**; strongest verified **India** coverage
  (`in`, INR) plus EU/US/remote. Requires "Jobs by Adzuna" attribution
  and a link back. (See licence note below.)
- **Careerjet** — free BYO affiliate key; broad India + global; official
  Python client. Affiliate model aligns with link-back behavior.
- **Remotive** — public no-auth remote backfill; **<=4 calls/day**,
  attribution required, no re-publishing (fine for a local single-user
  tool).
- Optional 6th: **The Muse** (free key, curated, has India).

**Universal paste-a-link / paste-a-JD** — first-class. The catch-all for
everything without a legal API: LinkedIn, Indeed, Google for Jobs,
Naukri, foundit, Wellfound, Instahyre, Hirist, YC Work-at-a-Startup.
Build on the existing "add a job by hand" path.

**Avoid (legal / ToS):** scraping LinkedIn, Indeed, Google for Jobs,
Naukri, foundit, Wellfound — no legal read path; they block bots.
**JSearch** works but re-serves scraped LinkedIn/Indeed/Google data; do
not ship by default.

**The honest India limit:** the dominant Indian boards have no legal API.
Auto-discovery in India covers tech/startup roles (ATS + Adzuna +
Careerjet); the broad market is **paste-a-link only**. Set this
expectation in the UI; do not pretend to cover Naukri.

## Honest fit (built, Stage 1)

Semantic (profile-centroid vs JD embedding, local, zero-token) + explicit
skills + role/company/location/red-flags, renormalized, **calibrated into
skip / weak / stretch / strong bands**. Surface the band on the inbox.
Weights live in `rubric.json`, tuned on the eval harness.

## Build sequence (when we resume)

1. **Eval harness first** — golden corpus + metrics. Measure before
   tuning. (We violated this once; not again.)
2. **Discovery** — the source layer above: 2-3 new connectors, country/
   remote filtering, curated seeds, first-class paste-a-link.
3. **Reuse-CV model** — `claim -> renderings`, per-job zero-LLM assembly,
   truth-constrained keyword alignment, LLM only on gaps.
4. **Show fit bands** in the UI.
5. **Outcome tracking** — applied -> interview -> offer.

## Deferred / non-goals

- Desktop packaging + BYO-key UI — after the engine is proven.
- Full evidence graph (STAR, evidence, defensibility) — only `claim` +
  `rendering` are needed now.
- MCP / agent-native surface — after the core loop works.
- Gig/freelance platforms (Upwork/Contra/Toptal) — OAuth-gated or no API;
  later. Paste-a-link covers them meanwhile.
- Scraping anything that forbids it. Permanent non-goal.
- Learning-to-rank / auto-apply. Permanent non-goals (measurement only).

## Open verification items

- **Jooble** and **Findwork** — ToS and India coverage unverified
  (signup/bot-gated). Do not integrate until someone reads the terms.
- **Adzuna licence** — free/personal use is fine for a local OSS tool; if
  Matchbox is ever monetized, their "commercial aggregation" clause may
  require a licence. Revisit only on monetization.
