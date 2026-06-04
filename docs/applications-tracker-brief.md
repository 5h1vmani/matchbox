# Design brief — Applications tracker (visual mockup)

> Paste everything below into claude.ai/code. It is self-contained: you do not
> need the rest of the repo. If you *are* running inside the `matchbox` repo,
> see §11 for the live files to read.

---

## 1. What this is

Matchbox is a **local-first, single-user job-search tool**. One person (a
job-seeker) tracks every role they are pursuing through a hiring pipeline. This
brief covers **one screen**: the **Applications tracker** — the page that
answers "where does every application stand, and what do I need to do today?"

We already have a working-but-plain version. This is a **design pass** to make
it genuinely good and visually consistent with the rest of the product (a CV,
cover letter, and LinkedIn banner already share one identity — see §4).

## 2. Deliverable (read this carefully)

* A **single self-contained `mockup.html`** — inline `<style>`, no build step,
  opens directly in a browser. Minimal vanilla JS only (collapse/expand, toggle
  an expanded row). **No backend, no framework, no data fetching.**
* Load fonts from Google Fonts:
  `https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap`
* **Hardcode the sample data in §8.** Show the populated dashboard, **plus** at
  least one **expanded/edit row state** and the **empty states** in §6.
* Add a short **`DESIGN_NOTES.md`** (or a top-of-file comment) explaining the
  layout decisions and any trade-offs.
* This is a **mockup to approve looks first.** Do not wire FastAPI/HTMX. But the
  intended interactions in §7 are real — design so there is room for them.

## 3. The user and the job-to-be-done

A stressed individual job-seeker, not a recruiter managing a funnel. The screen
must, in priority order:

1. **Tell them what to act on today** — follow-ups due, interviews coming up,
   drafts ready to send, applications gone stale.
2. **Show where everything stands** at a glance (the pipeline).
3. **Stay calm and honest** — never anxiety-inducing, never gamified. It shows
   stale and closed applications truthfully without nagging.
4. Let them **act fast inline** — advance a status, set a reminder, log a
   response, jot a note — without leaving the page.

## 4. Design system — MUST match exactly

This is a finished identity (the user's CV, cover letter, and LinkedIn banner
already use it). Do not invent a new palette.

**Typography**
* **IBM Plex Sans** — headings and body (weights 400, 500, 600).
* **IBM Plex Mono** — eyebrows, dates, numerals, status labels (400, 600).
* The signature treatment: **mono eyebrows** (uppercase, letter-spaced, small)
  over each section, and **1px hairline rules** to separate, never heavy boxes.
* Numerals (counts, days, dates) are **mono** — a "data-instrument" readout feel.

**Colour — zinc greyscale only. No blue, no indigo, no brand colour.**

| Role | Hex | Notes |
|---|---|---|
| Page background | `#fafafa` | |
| Card / surface | `#ffffff` | |
| Hairline / border | `#e4e4e7` | separators `#d4d4d8` |
| Heading text | `#09090b` | |
| Body text | `#3f3f46` | WCAG AAA |
| Label text | `#52525b` | WCAG AAA (7.73) |
| Muted / meta | `#696970` | WCAG AA (5.45) — do not go lighter |
| Chip bg / text | `#f4f4f5` / `#52525b` | border `#e4e4e7` |

**Semantic accents — used sparingly, as small dots/chips, never large fills:**
* Offer / positive: `#15803d`
* Needs-action / stale / overdue: `#a16207`
* Rejected / error: `#b91c1c`

Keep the page overwhelmingly greyscale and calm. Status is carried by a small
mono label + a dot; only **offer** earns green, only **overdue/stale** earn
amber. Everything else is grey. Closed rows are de-emphasised, not red.

**Layout:** desktop-first, content max-width ~**1024–1152px**, centred. Generous
whitespace, hairline dividers. Degrade gracefully on narrow widths.

## 5. Data model — what each application has

Real fields (use these names so it maps cleanly when we wire it later):

* `company`, `title`, `location`, `url` — the job.
* `status` — one of: **draft → applied → interview → offer → rejected → withdrawn**.
  (`rejected` and `withdrawn` are "closed".)
* `applied_at` — date applied (null while draft).
* `response_type` — null | `rejected` | `interview` | `offer` | `ghosted`.
* `response_at` — date of response.
* `next_action`, `next_action_at` — a reminder label + date (e.g. "Send", "Nudge",
  "Prep round 2").
* `notes` — free text.
* `cv_path`, `cover_path` — links to the tailored CV / cover PDF (may be null).
* `fit` (a.k.a. eligibility) — `{ band: strong | possible | stretch, reason: "…" }`.
  Shown as a chip. This is the honest fit assessment for the role.

**Derived fields (compute in the mockup from the above):**
* `days_in_stage` — days since `applied_at`.
* `needs_followup` — `next_action_at` is today or earlier.
* `is_stale` — status is `applied`, no response, and `applied_at` > 14 days ago.

## 6. Screen anatomy — what must be on the page

1. **Title bar** — "Applications" + a one-line summary, e.g.
   *"12 tracked · 3 need attention today · 1 interview"*.
2. **Pipeline strip** — a compact row of stage counts (Draft / Applied /
   Interview / Offer / Closed) plus **Response rate**. Big mono numerals, hairline
   separators. A glanceable funnel, not five heavy cards.
3. **Needs Attention** (the hero zone, top of page) — a prioritised list, in this
   order: interviews upcoming → follow-ups due today → drafts ready to send →
   stale (>14d, no response). Each item names the **one action** to take. If
   nothing is due, an encouraging empty state ("You're all caught up").
4. **All applications** — grouped by stage (Offer, Interview, Applied, Draft,
   Closed), each group **collapsible** with a count. Closed group collapsed by
   default and visually muted.
5. **Application row** — scannable in one line, expandable for detail/actions:
   * Company + role; location; **fit chip**; **status** control; `days_in_stage`
     (mono); `next_action` + date if set; links to **CV** / **Cover** if present.
   * Expanded: status control, follow-up (label + date), response logger, notes.
6. **Empty states** — (a) no applications at all; (b) an empty stage group (e.g.
   "No offers yet" — show this one, the user currently has none); (c) nothing in
   Needs Attention.

## 7. Interactions (intended — design for them; static mockup may stub)

* **Advance status** (draft→applied→interview→…): inline control on the row.
* **Set/clear a follow-up**: a label + date ("Nudge on 2026-06-15").
* **Log a response**: rejected / interview / offer / ghosted.
* **Add a note.**
* **Open CV / Cover** PDF.

In the mockup: show one row **expanded** demonstrating these controls; collapse
others. Vanilla JS for expand/collapse is fine. No persistence needed.

## 8. Sample data (hardcode this; illustrative)

```json
[
  {"company":"HighRadius","title":"Forward Deployed Engineer (Net New)","location":"Hyderabad / Remote India","status":"draft","fit":{"band":"strong","reason":"AI build + finance transformation overlap"},"cv_path":"cv.pdf","cover_path":"cover.pdf","next_action":"Send application","next_action_at":"TODAY","notes":"CV + cover ready, role render-verified open."},
  {"company":"Hightouch","title":"Technical Account Manager","location":"Remote","status":"applied","applied_at":"5 days ago","fit":{"band":"strong","reason":"Data + customer-facing"},"notes":"Confirm India eligibility — US E-Verify language in JD."},
  {"company":"Anthropic","title":"Forward Deployed Engineer","location":"Remote","status":"applied","applied_at":"34 days ago","fit":{"band":"stretch","reason":"Strong interest, geo uncertain"},"notes":"No response in 34 days — candidate for a nudge."},
  {"company":"Turing","title":"Financial Analyst","location":"Remote India","status":"applied","applied_at":"9 days ago","fit":{"band":"strong","reason":"FP&A + transformation fit"}},
  {"company":"Zscaler","title":"Sales Engineer","location":"Bengaluru","status":"draft","fit":{"band":"stretch","reason":"Pre-sales lane, light on quota"},"cv_path":"cv.pdf"},
  {"company":"Supabase","title":"Support Engineer","location":"Remote","status":"withdrawn","fit":{"band":"stretch","reason":"Coding-heavy"},"notes":"Closed — application deadline passed (Mar 2, 2026)."}
]
```

Add **one placeholder row** in the `interview` stage (e.g. `"Example Co" —
"Solutions Architect"`, `next_action:"Prep technical round"`, due in 3 days) so
the Interview state and a due-soon follow-up are visible. Keep the **Offer**
group empty to show that empty state honestly.

## 9. What "good" looks like (acceptance)

* A user lands and within ~3 seconds knows **what to do today** and **what stands
  where**.
* Feels **calm and premium**, not a busy CRM. Honest about stale/closed without
  alarm.
* **Unmistakably the same identity** as the rest of the product: IBM Plex,
  zinc greyscale, mono numerals, hairline rules.
* **WCAG AA minimum; AAA for body and labels** (the palette above already meets
  this — keep contrast).
* Dense yet readable; clear hierarchy; works ~1024–1152px and degrades on mobile.
* Opens as one HTML file, no build, with the sample data and the required states.

## 10. Avoid

* Any colour outside the palette; loud red; large coloured fills.
* Gamification — streaks, badges, progress confetti, urgency nags.
* Heavy UI frameworks, icon soup, drop-shadow-heavy "SaaS card" look.
* Tiny or low-contrast text; thin light-grey type on white (it must survive a
  glance — and JPEG screenshots).
* Kanban-by-default. A grouped list is the current model; if you propose a board,
  justify it in DESIGN_NOTES — but the **Needs-Attention focus zone is the
  priority**, not a five-column board.

## 11. If you are running inside the `matchbox` repo (optional)

Read these for the live tokens and data model, then still deliver the standalone
mockup:
* `src/matchbox/web/templates/base.html.j2` — Tailwind theme tokens, fonts.
* `src/matchbox/templates/html/cv.html` — the CV's exact design tokens (the look
  to match).
* `src/matchbox/web/routes/applications.py` — the real data model, statuses,
  pipeline/needs-attention logic, and HTMX endpoints.
* `src/matchbox/web/templates/applications/` — the current `index.html.j2` and
  `_row.html.j2` (the version we are improving on).
