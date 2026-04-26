# Matchbox UX — design rationale

This is the SSOT for *why* the dashboard looks and behaves the way it does. If
you find yourself second-guessing a design choice, this doc is the answer
(or the place to update before changing course).

## Users

Two users. Optimise for the daily one; don't actively hostile the cold-start one.

| User | Frequency | Tolerance for friction | Primary need |
|---|---|---|---|
| Operator (Shiva) | 5–50 actions/day for weeks | Zero | Triage speed; trust the routing |
| Cold-start visitor | One session, then decide | Low | "Can I see what this does in 30 seconds?" |

Everything below is justified by one of these two users.

## Information architecture

Four surfaces, no nested tabs. Hick's law: fewer top-level choices = faster
decision per click.

| Surface | Purpose | Mental model |
|---|---|---|
| **Inbox** | Daily triage | Email inbox |
| **Insights** | Funnel + cost + follow-ups + scans | Dashboard you look at weekly |
| **Profile** | Tunable scoring weights + structural read-out | Settings page that's worth visiting |
| **Settings** | API key, defaults, demo seed | Per-app preferences |

The previous Streamlit version had four tabs: Pipeline / Analytics /
Follow-ups / Scan history. Follow-ups and Scan history aren't pages of
content — they're cards. Merging them into Insights eliminates two clicks
per "what's the state of my pipeline" check.

## Inbox — the heart of the app

### Layout
- **Sticky filter bar** (top) — search, sort, state, tier, min score, starred.
- **Stats strip** (under filters) — N shown · counts by state · total spent.
  Always tells you what's on the table.
- **Table** (left, fills viewport) — virtualised by the browser, sortable header.
- **Slide-out detail panel** (right, ~580px) — opens on row click; doesn't
  navigate away from the list (Zeigarnik: keeps the list visible so you don't
  lose your scroll position or selection).
- **Bulk action bar** (fixed bottom-centre) — appears only when ≥1 row
  selected. Fitts's law: bottom-centre is the easiest place to hit with a
  mouse no matter where you scrolled.

### Keyboard model
Triage at scale is keyboard work. Every primary action has a single key:

| Key | Action | Why |
|---|---|---|
| `j` / `k` | Next / previous row | Vim/Gmail muscle memory |
| `Enter` | Open detail panel | Non-destructive; reversible |
| `Space` | Toggle row selection | Same as Gmail |
| `s` | Star current row | One-letter, single-tap |
| `a` | Mark selected applied | Imperative verb |
| `t` | Tailor selected | Imperative verb |
| `/` | Focus search | GitHub / Slack convention |
| `?` | Shortcut overlay | Universal convention |
| `Esc` | Close panel / overlay | Universal |

Shortcuts disabled when a text input is focused (so `j` in the search box
doesn't navigate rows). The `?` overlay reduces recall load — recognition
beats memorisation (Nielsen #6).

### Score visualisation
A horizontal coloured bar plus a number. Colour band:

- ≥ 4.0 emerald (bespoke threshold)
- ≥ 3.0 sky (template)
- ≥ 2.0 amber (canonical)
- < 2.0 slate (skip)

Same bands appear in the inbox table and the detail panel's score breakdown,
so the operator learns one mapping. The dimension breakdown uses simple
greyscale bars deliberately — the *total* deserves colour, the dimensions
are decomposition.

## Detail panel

Sections in order of action density (top = most-used):

1. **Header** — company, role, tier, state badge, "Open JD" + Star.
2. **Score** — total + 6-dim breakdown.
3. **Log outcome** — one-click `Interview / Offer / Rejection / Ghosted`. Buttons,
   not a dropdown. Loss-aversion-friendly colours: emerald for offer, lime
   for interview, rose for rejection.
4. **State change** — secondary state actions.
5. **Tailor** — single button → cost preview → confirm. Never bills the
   user without a confirmation step above the cost threshold.
6. **PDF preview** — inline iframe. Cover letter folded into a `<details>`
   so the CV stays primary.
7. **Metadata** — id, ATS, country, mode, applied/dream — small, dense,
   bottom-of-panel because rarely actioned.

### Cost transparency
The single most expensive UX failure was "click and discover you spent $20".
The fix:

- **Inline estimate in selection bar.** As you select rows, the bar shows
  estimated total cost based on tier (heuristic: bespoke ~$14, template
  ~$0.20). False precision avoided — the estimate is a midpoint of a range.
- **Preview before tailor.** Clicking "Tailor now" doesn't tailor — it
  shows a preview card with the cost range and a downgrade option.
- **Confirmation above threshold.** Above `MATCHBOX_COST_CONFIRM_USD` (default
  $1), the preview requires `confirmed=1` in the POST. Defence against
  accidental clicks (`hx-confirm` is *not* enough — server enforces).
- **Downgrade-in-place.** The preview card offers a one-click "↓ Downgrade
  to template" so the user can rescue an expensive misroute without leaving
  the panel.

### Gate violations
The previous flow logged gate failures to stdout where nobody read them.
Now: after a tailor, violations are surfaced as a rose card in the detail
panel, with the offending text highlighted. The PDF is still produced
(`gate_mode='warn'`) — the operator decides whether to use it, edit YAML,
or re-tailor.

## Insights

Cards stacked top-to-bottom by urgency:

1. **Action needed** (amber, only if non-empty) — Zeigarnik: unfinished work
   stays visible.
2. **Funnel** — 5 stages, count + rate. Visual hierarchy: count is large,
   rate is small.
3. **Cost** — Total / per-application / avg score. Adjacent so you can
   answer "is this getting cheaper or more expensive per outcome?" at a
   glance. Tier breakdown table sits below.
4. **Recent scans** — small table, low priority, but you want it when you
   want it.

No charts beyond the simplest (counts, rates). Pretty plots that need
interpretation cost more time than they save here.

## Profile

Two zones:

1. **Scoring weights** — six sliders, sum displayed live with colour-coded
   "should sum to 1" hint. Server-side validation rejects out-of-range
   values. `Normalize to 1.0` button removes manual arithmetic friction.
   `Save` writes to `profile.yaml` via ruamel round-trip (preserves
   comments + key order; atomic via temp + `os.replace`).
2. **Structural profile** — read-only counts (work entries, skills,
   archetypes). Editing structural data in a UI would lock us into a
   schema-following form generator; better to point at the YAML.

Re-scoring existing jobs after a weight change is *not* automatic. The
caption tells the user: re-run `matchbox score-job <profile> <id>` for any
job they want updated. Why not auto: weights changes are rare; re-scoring
500 jobs synchronously would lock the UI; surprise re-orderings in the
inbox would erode trust.

## Cold start

A fresh clone has only the `demo` profile. The journey:

1. Visit `/` → root redirects to `/p/demo/inbox` if demo has data, otherwise
   to `/system/welcome`.
2. Welcome page offers two choices: try the demo (`POST /system/seed-demo`
   loads 30 deterministic synthetic jobs) or create a real profile via CLI.
3. After seeding, redirect to demo's inbox so the user sees the UI alive
   immediately.

Fitts's-law note: the "Try the demo" button is the larger of the two
options because it requires the smaller commitment.

## Engineering principles applied

- **SSOT** for visual decisions: `web/filters.py` owns all formatting
  (currency, score, badges, relative time). Templates never hand-format.
- **DRY**: `_job_rows.html` is shared between full-page inbox and the
  HTMX rows partial. `build_inbox_context` is shared between full-page
  and partial routes — they cannot disagree about filtering.
- **Single responsibility per file**: each route module owns one concern
  (pages, jobs, bulk, profile, files, system).
- **Least privilege**: profile names are validated by regex at the
  FastAPI layer *and* by directory existence at the dependency layer.
  PDF serving requires the resolved path to stay under the job's output
  directory. Filename pattern restricted to `*.pdf|*.png`.
- **Pure-function adapters**: `tailor_view.estimate()` and `alternative_tier()`
  are pure functions over `Job`. Testable with no DB, no network.
- **Atomic writes**: weight save uses `tempfile.mkstemp` in same dir,
  fsync, `os.replace`. Cannot half-write profile.yaml.

## What's intentionally not built

- Real-time WebSocket updates. The pipeline isn't multi-user; HTMX polling
  is enough if needed.
- Dark mode. Single user, single environment, not worth the design cost.
- Mobile responsive. Triaging 200 jobs on a phone is not a real workflow.
- Rich text editor for cover letters. Cover letters are LLM-generated;
  if the operator wants to edit, they can edit the YAML/PDF source.
- Drag-and-drop reordering. Sort columns + filters cover the same need.

## Future moves (numbered for tracking)

1. Live re-score preview on weight change (delta table of top 10 jobs).
2. Tailor "regenerate just this bullet" for surgical edits.
3. Saved filter presets per profile.
4. Email digest of follow-ups.
