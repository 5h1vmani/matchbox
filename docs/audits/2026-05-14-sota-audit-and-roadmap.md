# SOTA audit and v1/v2 roadmap for open-sourcing Matchbox

**Date:** 2026-05-14
**Author:** Audit pass against current `main` (commit `7bc9cf3`)
**Purpose:** Identify the wedge that makes Matchbox worth open-sourcing now, decide what to ship in v1 vs defer to v2, and call out gaps honestly.
**Scope:** UX, backend logic, and open-source readiness. Not a security review — see [SECURITY.md](../../SECURITY.md).

---

## 1. Executive summary

Matchbox is a precision job-application tool. It does the *narrow middle* of the funnel very well: probing 3 ATS types, deterministic 6-dimension scoring, cost-tiered tailoring, and outcome tracking — all local-first with no auth and no cloud sync. The wedge is real: **private + cost-honest + quality-over-quantity for technical jobseekers**. No mainstream tool (LinkedIn, Indeed, Teal, Huntr, Simplify) occupies that ground.

The audit finds three classes of gaps:

1. **Onboarding wall for non-operator users.** Profile setup requires hand-editing YAML. This is fine for Shiva and the few hundred developers who will be early adopters. It is fatal for the next 10x of users.
2. **Discovery surface is too narrow to be useful unmodified.** 20 hardcoded orgs across 3 ATS types covers a niche (AI infra startups). Most jobseekers don't share that target set.
3. **The "track" half of the funnel has a critical missing layer: email response detection.** Without it, the tool depends on the user remembering to log every response, which they will not do.

**Recommendation:** Ship v1 now. Don't broaden, sharpen. Five surgical fixes turn the existing pipeline into something a stranger can use in 15 minutes. v2 then adds the dream-job-gap and interview-prep layers that nobody else does well — that is where Matchbox gets *non-substitutable*.

The two things to resist: building generic features that LinkedIn/Teal already have, and turning the YAML-driven config into a thousand-knob UI.

---

## 2. What works today (verified against code, not README)

Confirmed from `src/matchbox/` walk:

| Area | Reality | Notes |
|---|---|---|
| ATS probers | Greenhouse, Lever, Ashby | README claims 4 (includes Workable); Workable not implemented. **ALERT.** |
| Org coverage | 20 hardcoded companies (`discovery/sources.py:KNOWN_SOURCES`) | Substring match on company name. User cannot add orgs via YAML. |
| Scoring | 6 dimensions, deterministic, weighted per profile | `comp_score` and `cultural_score` are placeholders hardcoded at 3.0. **ALERT.** |
| Tier router | bespoke / template / canonical / skip | Cost-tier mapping is sound. |
| Exclusions | Per-sector with per-country overrides | Crypto, defense, etc. Applied at scan time. |
| Tailoring | Single Sonnet 4-6 call returns structured JSON; deterministic gates after | Cost tracked per call. 6 voice gates run post-generation. |
| Anchor packs | Pre-approved bullets per role family | Selected by LLM in template tier; falls back to `work_history.bullets`. |
| Web UI | 4 surfaces (Inbox, Insights, Profile, Settings), HTMX-driven | Keyboard-first. Cmd+K palette shipped. |
| Outcome states | 11 states from `evaluated` → `offer`/`rejected` | Manual logging via CLI or web form. |
| Analytics | Funnel, cost-per-stage, follow-up candidates | Insights page renders these. |
| Storage | One SQLite per profile + YAML SSOT | Append-only pipeline state; identity in YAML. |
| Cost guardrails | Server-enforced $1 confirm; bulk capped at 5 | Real, not theatre. |

This is more than most v1 open-source projects ship. **The product half of the work is done.** What's left is the on-ramp, the discovery breadth, the response loop, and the open-source furniture.

---

## 3. What a jobseeker actually needs (jobs-to-be-done)

A SOTA tool would serve eight jobs. Matchbox today fully serves three, partially serves three, and ignores two.

| # | Job to be done | Matchbox today | SOTA reference |
|---|---|---|---|
| 1 | Discover relevant openings | Partial — 20 orgs, 3 ATS | LinkedIn / Indeed / Wellfound |
| 2 | Short-list (dedup, filter, comp, visa) | Partial — filters strong, comp/visa weak | Otta / Wellfound |
| 3 | Decide where to spend effort (match signal) | **Full** — best-in-class for this niche | Teal AI score (weaker) |
| 4 | Apply (autofill, tailored materials) | **Full** for materials; no autofill | Simplify Jobs autofill ext |
| 5 | Track responses | Partial — manual logging only | Huntr / Teal kanban |
| 6 | Follow up at the right time | Partial — follow-up list exists, no nudges | Streak CRM cadence |
| 7 | Prepare for interviews | **None** | interviewing.io / Exponent |
| 8 | Reflect and improve over time | **None** | (no clear leader) |

The strategic question is which of jobs 1, 2, 5, 7, 8 to invest in for v1 vs v2.

**Position:** Job 5 (tracking) is the single most leveraged add. Without it, every prior stage's data is incomplete and analytics lies. The project's own [blind-spots history doc](../history/2026-04-21-blind-spots.md) already identified this in April. Outcome logging shipped — what's missing now is automatic *response detection* so users don't have to log manually.

---

## 4. UX gaps that block real-world use

Ranked by severity for a new user landing on the repo on day one.

### 4.1 The YAML wall (severity: critical)

A non-developer cannot edit `profile.yaml`. Even a developer is hostile to it after the third edit. Today the web UI lets the user change *only scoring weights* — not candidate, work_history, skills, projects, filters, or compensation.

**Why it matters:** The 60-second demo works without a profile. The next step ("real usage") requires editing 200+ lines of YAML across two files plus a markdown stories file. Drop-off is enormous.

**v1 fix:** Web-UI profile editor for at minimum the `candidate`, `targets`, and `filters` sections. Keep YAML as the source of truth on disk; the UI is a form over it (atomic save with temp+fsync+replace already exists, reuse it).

### 4.2 No JD-from-URL capture (severity: high)

Real jobseekers find jobs on LinkedIn, Twitter, friends' Slack messages — not by scanning Greenhouse. Today there is no path to paste a URL or JD text and have it scored.

**v1 fix:** A `+ Add job by URL/paste` button on the Inbox. Server fetches the URL, extracts JD text (or accepts pasted text directly), scores it, drops it into the pipeline. No need to support every ATS — just accept any URL.

### 4.3 Discovery feels empty without a 5-minute setup (severity: high)

`matchbox scan alice` against the hardcoded 20 orgs gives most users nothing. They need their own org list.

**v1 fix:** Move `KNOWN_SOURCES` into `people/{name}/sources.yaml` (with the existing list as the default seed). Web UI to add/remove orgs. One-line ATS-type entry: `greenhouse: anthropic`.

### 4.4 Onboarding has no "what is this" landing (severity: medium)

`/system/welcome` exists but the entry experience for a stranger is `pip install` → `seed-demo` → CLI. There is no screenshot or GIF in the README, no hosted demo, no "tour" overlay in the seeded demo profile.

**v1 fix:** Two screenshots + one 30-second GIF in README. A two-step tour the first time `/p/demo/inbox` loads (existing palette/help infra makes this cheap).

### 4.5 Response loop is manual (severity: medium → high after volume)

User must remember to log every response. They will not.

**v1 fix (lightweight):** A "Paste email" textbox on the Inbox that runs a classifier (regex first, LLM fallback only if confidence low) to detect `interview / rejection / offer` and which job it belongs to (match against company+role tokens). Suggest, don't auto-apply.

**v2 fix (heavier):** Optional IMAP read-only integration. Local credentials, never leaves the machine. Same classifier.

### 4.6 Smaller UX friction (severity: low, but cumulative)

* No "snooze" on a job (push it back N days).
* No way to mark a JD URL as stale (the `url_http_status` field is in the schema, no UI to revalidate).
* No saved filter presets (already on the project's own [future-moves list](../ux-design.md)).
* No regenerate-just-this-bullet (also on the future-moves list).

---

## 5. Backend / data gaps

### 5.1 Placeholder scores

`comp_score` and `cultural_score` are hardcoded at 3.0 in `scoring/rubric.py`. The README markets a 6-dimension rubric. Two of the six are stubs. This is the most user-trust-fragile thing in the codebase.

**v1 fix:** Either (a) parse comp from JD text when stated and score against the user's `compensation` target, falling back to a *displayed* "no data" state instead of a fake 3.0; or (b) drop both dimensions from the rubric until they are real, and re-weight to 4 dimensions. **Do not ship v1.0 of an OSS tool with placeholder scores masquerading as real.**

### 5.2 No dedup across boards

Same job posted on Greenhouse and a company careers page enters twice. `ats_probe.py` has no dedup; the DB layer dedups by URL only, so two URLs for the same role both survive.

**v1 fix:** Hash on `(normalized_company, normalized_role)` at insert; mark duplicates as such, surface the canonical one.

### 5.3 No rate limiting, no caching

`ats_probe.py` does one `httpx.get` per board per scan, no backoff. Greenhouse and Lever will tolerate this at low volume; Ashby less so. No HTTP cache headers respected.

**v1 fix:** Two-line ETag + last-modified cache per source in SQLite. Polite default delay between requests (e.g. 250ms).

### 5.4 ATS coverage

3 types covers maybe 30% of the open-job universe. Adding Workday (the biggest gap) is hard — it's not a clean public API and rate-limits aggressively. SmartRecruiters and iCIMS are easier.

**v1 fix:** Add the README-claimed Workable prober. (Or update README to say 3.) **ALERT.**
**v2 fix:** Add SmartRecruiters; consider iCIMS. Workday is a v3 conversation.

### 5.5 No background scheduler

User must run `matchbox scan` manually. The README says daily; the CLI offers no `--cron` or service-install option.

**v1 fix:** Document the cron one-liner. (`launchd` plist for mac, systemd unit for linux.) Don't build a scheduler — document one.

### 5.6 Stories.md is loaded but underused

`person.py` reads `stories.md` as plain text. It's intended as STAR+R career stories the LLM can draw on, but I see no evidence the tailor flow injects them into the Sonnet prompt with structure. Worth verifying — out of scope for this audit, flagging for v1 investigation.

### 5.7 Cost ledger is per-application, not session-level

Cost is summed per application in analytics, but a user mass-tailoring 5 jobs sees no live total mid-batch. Bulk tailor is capped at 5, but a user wanting to know "what did I spend today" has no surface.

**v1 fix:** A small cost-this-week panel on Insights. Existing analytics aggregator handles the math; add the widget.

---

## 6. Open-source readiness

The repo has the right *furniture*: MIT license, CI badge, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, ADRs. Tooling is strict (ruff + mypy strict + pytest). This is better than most OSS launches.

What's missing:

| Item | Status | Action for v1 |
|---|---|---|
| ROADMAP.md | None — implicit in [ux-design.md "future moves"](../ux-design.md) | Promote to top-level `ROADMAP.md` with v1/v2 split |
| GOVERNANCE.md | None | Add: BDFL model, decision process, ADR convention |
| .github/ISSUE_TEMPLATE/ | Unknown — verify | Bug report, feature request, ATS prober request |
| .github/PULL_REQUEST_TEMPLATE.md | Unknown — verify | Aligned with CONTRIBUTING |
| Screenshots / GIF in README | None | Two screenshots + one GIF |
| Comparison vs alternatives | None | One-paragraph "vs Teal / Huntr / Simplify" in README |
| Hosted demo | None | Optional for v1; high impact, medium effort |
| Discussions enabled | Unknown | Enable on GitHub; seed with 3 starter threads |
| Code-of-conduct enforcement plan | Unknown | One line in CODE_OF_CONDUCT.md naming the responder |

The hardest open-source question Matchbox faces is **single-user-by-design vs the way OSS users will want to deploy it**. ADR-0005 commits to localhost-only, no auth. Users will try to host it on a VPS for their phone. Document this clearly with a "deploying behind Tailscale/Caddy" recipe, but **don't bend the architecture**. The single-user assumption is part of the wedge.

---

## 7. v1 scope — what to ship to open-source

**Principle:** Polish what works. Close the five gaps that turn the demo into a tool a stranger can use unaided. Ship in 2-3 weeks of focused effort.

### v1 — must ship

1. **Profile editor in the web UI** (candidate, targets, filters sections). Reuse existing atomic-save infra. Sections 4.1.
2. **Add job by URL/paste** on the Inbox. Section 4.2.
3. **User-editable sources list** at `people/{name}/sources.yaml` plus simple UI. Section 4.3.
4. **Fix the placeholder scores.** Either parse comp from JD or drop both dims and re-weight. Section 5.1.
5. **Workable prober** (matches README claim) or update README to say 3 ATS types. Section 5.4.
6. **README screenshots + GIF.** Section 4.4.
7. **ROADMAP.md** committed to repo with this audit's v1/v2 split as the source of truth.
8. **Issue + PR templates** under `.github/`.
9. **Comparison paragraph** in README ("how Matchbox differs from Teal / Huntr / Simplify").
10. **Cron documentation** for daily scan (mac launchd + linux systemd). Section 5.5.

### v1 — should ship if cheap

1. **Dedup across boards** by `(normalized_company, normalized_role)`. Section 5.2.
2. **ETag + polite-delay** in ATS probers. Section 5.3.
3. **Paste-email response classifier** (regex first, LLM only if low confidence). Section 4.5 lightweight.
4. **Snooze and saved filter presets**. Section 4.6.
5. **Cost-this-week widget** on Insights. Section 5.7.

### v1 — explicit non-goals

* No multi-user, no auth, no cloud sync. (ADR-0005.)
* No mobile-responsive layout. ([ux-design.md](../ux-design.md) explicit non-goal.)
* No interview prep, no skill-gap analysis, no dream-job comparison. (Pushed to v2.)
* No browser extension. (v2 conversation.)
* No additional ATS types beyond Workable. (v2 conversation.)

### v1 — definition of "done"

A stranger clones the repo on day one. Inside 15 minutes they have a profile, 10+ scored jobs on their inbox, and a path to tailor and track them. They never edit YAML.

---

## 8. v2 scope — what makes Matchbox non-substitutable

v1 brings Matchbox to parity with the niche-tool tier (Teal-lite for technical users). v2 is where it does what no one else does well.

### v2 — dream-job gap analysis

The user defines a **dream profile** separate from their current profile. The system continuously compares:

* skills present vs skills demanded by the top-decile of dream-tier jobs scanned
* title progression patterns in the scanned data
* comp expectation vs market

Output: a *gap matrix* with a small number of concrete, evidence-anchored recommendations ("In 14 of 20 ML Engineer roles at dream-tier orgs scanned in the last 30 days, JD mentions Triton kernels; you have no evidence of this in `skills` or `projects`. Consider X."). This requires real skill ontology — not LLM hand-waving. Build the ontology from the scanned JD corpus, not from a generic taxonomy.

### v2 — story-to-claim engine

Stories.md exists. v2 uses it as a structured evidence store. When the tailor flow needs to make a claim ("led migration of 30M-row table"), it pulls from a story with a strength signal; when no story supports a claim, the gate refuses to make it. This is **hallucination prevention by construction**, not by post-hoc gate.

### v2 — interview prep loop

When a job moves to `interview` state, surface:

* the JD's key competencies (already extracted during scoring)
* which of the user's stories map to each competency
* 3-5 likely behavioral questions per competency (LLM-generated, user-editable)
* a practice mode that asks them and records the user's spoken answer (browser MediaRecorder API)
* post-practice transcription + STAR-completeness feedback

Reference signal: this is what interviewing.io and Pramp charge for. Matchbox does it for free, locally, anchored to the user's own stories.

### v2 — email integration (IMAP read-only)

Section 4.5 heavyweight version. Optional. Credentials encrypted at rest in the OS keychain (Keychain on mac, libsecret on linux). Read-only IMAP; classify and link responses to jobs; never auto-send.

### v2 — referral graph (carefully)

The user pastes their network (LinkedIn export CSV). When a high-scoring job lands, surface which of their network is at that company. No outbound automation, no scraping — just connection discovery within data they already have.

### v2 — non-goals

* No social feed. No public profiles. No "see who applied."
* No paid tier on the OSS itself. Hosted multi-user is a separate conversation that doesn't compromise the OSS posture.

---

## 9. v3+ — parking lot

Things worth revisiting but not now:

* Workday + iCIMS probers (hard, high-coverage)
* Mobile web (after v2 settles)
* Multi-profile-per-machine UX (today possible via filesystem; could be sharper)
* Recruiter mode (inverted: scan inbound applications)
* Salary intelligence data import (Levels.fyi CSV)
* Cover-letter regenerate-by-bullet (already on future-moves list)
* Browser extension (one-click capture from any JD page)

The discipline here is: do not let v3 grow before v1 ships and v2 has real-user signal.

---

## 10. How a SOTA product team would handle this

### How Apple would do it

Pick *one* user. Build for them with obsessive depth. Cut everything that doesn't serve them. Ship a flawless v1 with 5 features instead of a wobbly v1 with 25.

Translated to Matchbox: the user is **"a technical jobseeker who applies to 3-10 jobs a week, who values their privacy, who edits config files, who would rather get one offer they want than ten offers they don't."** Every v1 decision passes through that filter. The "YAML wall" fix above does not move the target user — it just removes a needless paper cut.

### How Anthropic would do it

Helpful, honest, harmless. Trust over flash. Cost-transparent. Defaults that protect the user. Iterate from real signal, not from the loudest voice on Twitter.

Translated to Matchbox: the existing cost-confirm UX is exactly right; do not water it down. The placeholder `comp_score = 3.0` violates the honest principle and must be fixed. The "tailor-bespoke for dream-tier only" router design is exactly the right *helpful* default. **Don't fix what is already aligned. Fix what isn't.**

### What both would refuse to do

* Ship a half-built feature to look competitive with LinkedIn.
* Add a chat sidebar.
* Add a leaderboard.
* Make scoring "AI" when deterministic Python suffices.
* Open a hosted SaaS before the local product is loved.

### What both would invest in

* Loading the first-time experience with absurd care.
* Saying no, in writing, to the next ten feature requests.
* Reading every issue and discussion personally for the first 90 days post-launch.

---

## 11. Cost and time framing

A rough effort estimate for v1 (single maintainer, focused weeks):

| Block | Effort | Notes |
|---|---|---|
| Profile UI editor | 3-4 days | Reuses atomic-save infra |
| URL/paste capture + JD extractor | 2-3 days | `readability-lxml` covers most cases |
| User-editable sources.yaml + UI | 1-2 days | Largely YAML schema + form |
| Fix placeholder scores | 2-3 days | Decide: parse comp, or re-weight |
| Workable prober | 1 day | Pattern matches existing probers |
| README screenshots + GIF | 0.5 day | |
| ROADMAP.md, templates, comparison | 0.5 day | |
| Cron documentation | 0.5 day | |
| Dedup, ETag, snooze, presets, classifier, cost widget | 4-6 days total | Pick which of these survive scope |
| Polish + release prep | 2-3 days | |
| **Total** | **~3 weeks focused** | |

This assumes Shiva is the only engineer. With one collaborator on the periphery (issues, docs, screenshots), it compresses to ~2 weeks.

v2 is a 2-3 month project after v1 has 30 days of real-user signal. Don't start v2 work until that signal exists.

---

## 12. Open questions for the maintainer

These need a decision before v1 work starts:

1. **Hosted demo, yes or no?** Adds onboarding power; adds ops surface. A Fly.io / Railway one-click that runs the `seed-demo` profile only (no real API key) might thread the needle.
2. **Placeholder scores: parse or drop?** Decide per Section 5.1 before any v1 code lands.
3. **Naming.** Is "Matchbox" final? It's good. Check for trademark conflicts in the recruiting space.
4. **Telemetry, opt-in.** A single `matchbox version` ping at install time so we know how many people are using it. Anonymous, opt-in default off, documented in plain English. Yes/no?
5. **License of `sources.yaml` default seed.** The 20 hardcoded orgs are public ATS slugs; safe. Worth a one-line note in CONTRIBUTING.
6. **Discussions vs Issues policy.** Soft preference: "feature requests in Discussions, bugs in Issues." Document it in the templates.
7. **Single-maintainer vs invited collaborators.** v1 is solo-feasible. Post-launch, is there an invited circle of 2-3 trusted contributors with merge rights? Worth deciding now.

---

## 13. Risks

* **Cost surprises despite guardrails.** A user with `MATCHBOX_COST_CONFIRM_USD` set high (or `0`) burns budget. Default is $1, which is safe; consider hard-clamping the env var minimum at e.g. $0.10.
* **ATS terms of service.** Greenhouse/Lever/Ashby public APIs are read-only and rate-tolerable, but no formal blessing. Document this clearly. Workday and similar would be a different legal posture entirely.
* **Solo maintainer burnout.** OSS projects die from this more than from bad code. Build a discussions habit, batch responses, set an "office hours" cadence early.
* **The YAML wall** (already covered) is the single largest user-acquisition risk.
* **Placeholder scores** (already covered) is the single largest user-trust risk.
* **First negative review** will land somewhere — Hacker News, Reddit. Pre-write a "what Matchbox is not" section now so the response is calm, not defensive.

---

## 14. Decision

Ship v1 per Section 7. Hold v2 until 30 days of real-user signal. Reject scope creep with cited reference to Section 8 and Section 9. Re-read this document before saying yes to anything not on it.

The wedge is **private + cost-honest + quality-over-quantity for technical jobseekers**. Every v1 decision serves that wedge or does not happen.
