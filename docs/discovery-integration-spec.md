# Discovery — engineering integration spec

**For:** an Opus build agent (assume you have NOT seen this repo). **Goal:**
port the design team's **Discovery** surfaces (`designs/v1.1/`) into matchbox
**pixel-exact and behaviour-exact**, wired to our backend. This is the exact
same job we already did for the tracker (`designs/v1/` → `frontend/` +
`src/matchbox/tracker/` + `/api/*`) — repeat that recipe.

> **Non-negotiable: pixel match.** The output must be visually identical to the
> design prototype (`designs/v1.1/Discovery.html`). You prove it with a
> screenshot diff before you call this done (§9). The recipe that guarantees it:
> **copy their CSS verbatim, port their components byte-identical, build the
> backend underneath.** Do not redesign anything.

---

## 0. What already exists (bootstrap — don't re-discover)

We already shipped the **tracker** with this exact approach. Read these to learn
the patterns, then mirror them for discovery:

- **Frontend** lives in `frontend/` — Vite + React 18 + TypeScript, builds into
  `src/matchbox/web/static/app/` (gitignored). It self-hosts Hanken Grotesk +
  JetBrains Mono via `@fontsource`, and uses **`lucide-react`** behind a small
  `frontend/src/ui/icon.tsx` that exposes `<Icon name="kebab-case" />` (reuse
  it). The tracker design CSS was **copied verbatim** to
  `frontend/src/styles/{colors_and_type.css,mb.css}`; components were ported
  byte-identical from `designs/v1/*.jsx` into `frontend/src/{ui,screens}/*.tsx`
  with `window.*` globals swapped for ES imports. `frontend/src/App.tsx` is the
  tracker shell; `frontend/src/store/useApps.ts` is API-backed; the in-memory
  port is kept in `useAppsMemory.ts`. **Study these as the template.**
- **Backend** — FastAPI. `src/matchbox/tracker/{rules,repo,service}.py` is the
  tracker's pure-rules / DAL / action-effects split; `src/matchbox/web/routes/api.py`
  is the JSON API (returns the view-model directly; the repo serializes DB →
  view-model). `src/matchbox/web/deps.py` resolves the **active profile per
  request** (cookie `mb_profile`); `ConnDep`/`ProfileDep` are the deps. The SPA
  is served at `/tracker` via a FileResponse in `src/matchbox/web/app.py`.
- **DB** — SQLite per profile (`people/<slug>/matchbox.db`). Migrations are
  `src/matchbox/core/NNN_*.sql`, auto-discovered; `target_version()` bumps when
  you add a file. The `migration` runner applies each once. The **`job`** table
  is the role pool: `id, source(FK ats_source), company, title, location, url,
  apply_url, jd_text, requirements_json, posted_at, fetched_at, country, remote,
  status('new'|'scored'|'selected'|'tailored'|'applied'|'skipped'|'rejected'),
  score (REAL), score_breakdown_json`. The **`application`** table is the
  tracker pipeline (post-v5: `stage, salary, source, starred, has_draft,
  updated_at, next_action*`, child tables `app_note/app_contact/app_event`).
- **The run model (the tailor hand-off)** — `src/matchbox/scoring/runs.py`
  `create_run()` writes `runs/<run-id>/work-queue.json` + `run`/`run_job` rows;
  the user copies a "process run X" prompt into Claude Code, which tailors and
  writes back. **Runs stay manual** (no auto-runner). Discovery's `Tailor CV`
  decision reuses this.
- **Where the reads come from** — `score_breakdown_json` on a scored job already
  carries the scoring breakdown and (for judged jobs) an `eligibility` object
  `{status, reason}` (produced by our strict-India eligibility judging). **Verify
  the actual JSON shape against a real scored job in `people/shiva/matchbox.db`
  before writing the serializer** (`SELECT score, score_breakdown_json FROM job
  WHERE score_breakdown_json IS NOT NULL LIMIT 3`).

## 1. The design to port (`designs/v1.1/`)

Read the handoff `designs/v1.1/Engineering Handoff.html` §D1–D4 (Discovery) in
full. The shipping surfaces:

- **Today's roles — the review queue** (default): a *finite* set reviewed **one
  card at a time** with a shrinking progress bar. Only `eligible|unclear` +
  `open|closing` + undecided roles enter; closing-soon floats to the front.
  Card = header (mono, title, company·location·salary, freshness, source), the
  **Fit + Eligibility reads side by side** (the crux), CV coverage bar, a pulled
  JD line + *Read full description*, and the decision row **Dismiss / Track /
  Tailor CV** (primary). Keyboard: `X` dismiss, `T` track, `⏎` tailor, `↓` skip.
  Every decision → toast with **Undo**. Ineligible/closed roles are
  **pre-removed** into a dimmed collapsible **"Set aside for you"** group with an
  honest reason — the same treatment as the tracker's "Going cold."
- **Browse** (`/discover/browse`): calm filters (fit, freshness, `Eligible only`
  default-on, `Remote`) + a tile grid + **multi-select → sticky batch bar**
  (*Track all / Dismiss / Tailor N CVs*).
- **Watchlist** (`/discover/watchlist`): companies worth watching with no role
  today; "N open"/"watching" tags.
- **JD drawer** (overlay): the deeper read; reuses the tracker's `.scrim/.drawer`.

**Files** (`designs/v1.1/`): `discovery.css` (verbatim copy), `dui.jsx` (atoms:
`Icon, MonoLogo, FitMeter, EligibilityRead, Freshness, Coverage`), `Review.jsx`,
`Browse.jsx`, `WatchlistJD.jsx`, `DiscoveryApp.jsx` (shell + decision handler +
batch + toast), `discovery-data.js` (`window.ROLES`, `window.WATCH`). The shared
`colors_and_type.css` + `mb.css` are unchanged from v1 (already in `frontend/`).

## 2. The pixel-match recipe (follow exactly)

1. **CSS verbatim.** `cp designs/v1.1/discovery.css frontend/src/styles/discovery.css`.
   Confirm `mb.css`/`colors_and_type.css` are byte-identical to v1.1 (they are);
   if v1.1 changed them, re-copy. Import `discovery.css` in the discovery entry.
2. **Port components byte-identical.** For each `*.jsx`, preserve **every
   className, inline style, DOM structure, and copy string**. The only changes:
   `window.X` globals → ES imports; the Lucide-CDN `Icon` → the existing
   `lucide-react` `Icon`; `window.ROLES/WATCH` → a `data/discoverySample.ts`
   fixture (port `discovery-data.js`). Do **not** "improve" markup.
3. **Build green**, then **screenshot-verify** against the prototype with sample
   data (§9), before wiring the backend. This is the milestone that proves the
   port.
4. Only then wire the store to the real API and serve it.

## 3. Frontend structure (mirror the tracker)

- `frontend/src/styles/discovery.css` — verbatim copy.
- `frontend/src/discovery/types.ts` — `Role`, `WatchedCompany`, `FitRead`,
  `EligibilityRead`, `Coverage`, `FitLevel`, `EligibilityStatus`, `Freshness`,
  `Decision`, `DecisionInput`, `DiscoveryActions` (from handoff §D3/§D4).
- `frontend/src/discovery/dui.tsx` — port `dui.jsx` (FitMeter, EligibilityRead,
  Freshness, Coverage, MonoLogo). Reuse the shared `Icon`.
- `frontend/src/discovery/screens/{Review,Browse,WatchlistJD}.tsx` — port.
- `frontend/src/discovery/DiscoveryApp.tsx` — port the shell + decision handler.
- `frontend/src/discovery/data/discoverySample.ts` — port `discovery-data.js`
  (the dev/offline fixture; also the screenshot-parity fixture).
- `frontend/src/discovery/store/useDiscovery.ts` — API-backed store exposing
  `decide`/`batchDecide` + the role lists; keep an in-memory `useDiscoveryMemory`
  seeded from the sample (mirror the tracker's two-backend split).
- `frontend/src/discovery/api/client.ts` — fetch wrappers for `/api/discovery/*`.

**Shell routing:** the prototype has two shells (tracker `App`, `DiscoveryApp`)
that cross-link via the sidebar. Keep that. In `frontend/src/main.tsx`, render
`DiscoveryApp` when `location.pathname.startsWith("/discover")`, else the tracker
`App`. FastAPI serves the SPA `index.html` at `/discover` (and `/discover/*`) as
well as `/tracker` (add the route in `app.py`). Sidebar cross-links are plain
`<a href="/discover">` / `<a href="/tracker">`. Match whatever internal nav the
prototype's `DiscoveryApp.jsx` uses (likely state, not URLs) — replicate it.

## 4. Data model → backend serializer (the crux)

The frontend `Role` shape is fixed (handoff §D3 + `discovery-data.js`). Serialize
each scored `job` → `Role`. **The UI never computes fit/eligibility/coverage —
they come from the service.** Mapping:

| Role field | From matchbox |
|---|---|
| `id` | `str(job.id)` (the prototype uses `"role-N"`; a bare id string is fine) |
| `company`, `title`, `location` | `job.company`, `job.title`, `job.location` |
| `remote` | `bool(job.remote)` |
| `salary` | **not stored on `job` → `null`** (display "undisclosed"). Flag: could parse from JD later |
| `source` | a display string from the `ats_source` (type/company) or `"Careers page"` default |
| `postedDaysAgo` | days since `job.posted_at` (reuse the tracker's date helpers) |
| `link` | `job.apply_url or job.url` |
| `jd` | `job.jd_text` split into paragraphs (`string[]`) |
| `fit` | `{level, reason}` — derive `level∈{strong,good,stretch}` from `job.score` thresholds; `reason` from `score_breakdown_json` (an honest one-line) — **inspect the real shape; propose thresholds; flag if reasons are absent** |
| `eligibility` | `{status, reason}` from `score_breakdown_json["eligibility"]`; **map our status values → `eligible|unclear|ineligible`** (verify the actual enum) |
| `coverage` | `{covered,total}` from a requirement match if present, else `null` |
| `freshness` | `open|closing|closed` — see §5 (default `open` if unknown) |
| `closingInDays` | from a stored deadline if `closing`, else `null` |
| `mono` | reuse `tracker/rules.py::mono_for(company)` |
| `decision` | from the new `discovery_decision` (see §6); `null` = undecided |

`WatchedCompany` ← the new `watchlist` table (§6): `{company, note, status, openRoles, mono}`. `openRoles` = count of open scored eligible jobs at that company.

**Reality to honor (and flag clearly):** only **scored/judged** jobs have
`fit`/`eligibility`. The discovery API serves **scored** jobs; unscored jobs are
out of the queue (they need an upstream Claude-Code scoring run — the same
eligibility-judge pipeline we already have). Do **not** try to score in the UI or
the request path. If `people/shiva/matchbox.db` has few scored jobs, that is
expected — verify the UI with the sample fixture (§9) and wire the serializer so
it renders whatever scored jobs exist.

## 5. Freshness

Add `freshness TEXT` and `closes_at TEXT` to `job` (migration v6), defaulting to
`open`/null. Populating them is the render-based check (`scripts/verify_open.py`,
which already returns open/closed + deadlines) run periodically/on-demand — **out
of scope for this build** (default everything to `open`, leave the columns for
that job). Serializer: `closed` → set-aside; `closes_at` within N days →
`closing` + `closingInDays`; else `open`.

## 6. Migration v6 + decisions API

**`src/matchbox/core/006_discovery.sql`:**
- `ALTER TABLE job ADD COLUMN discovery_decision TEXT;`  -- null|tracked|dismissed|tailoring|watch
- `ALTER TABLE job ADD COLUMN skipped_on TEXT;`          -- ISO date; if == today, drop from today's queue
- `ALTER TABLE job ADD COLUMN freshness TEXT;`           -- open|closing|closed (default open at read time)
- `ALTER TABLE job ADD COLUMN closes_at TEXT;`
- `CREATE TABLE watchlist (id INTEGER PK, company TEXT NOT NULL UNIQUE, note TEXT, status TEXT NOT NULL DEFAULT 'watching', created_at TEXT DEFAULT (…now…));`

**`src/matchbox/discovery_api/` (new module, mirror `tracker/`):** `rules.py`
(membership: `in_queue`, `in_set_aside`, the sort order from §D4), `repo.py`
(serialize job → Role; load queue/browse/watchlist; the decision writes),
`service.py` (the decision effects).

**`src/matchbox/web/routes/discovery.py`** (prefix `/api/discovery`):
- `GET /api/discovery/queue` → today's queue (ordered) + the set-aside group + a done-tally.
- `GET /api/discovery/browse?fit=&fresh=&eligible_only=&remote=` → tiles.
- `GET /api/discovery/watchlist` → watched companies.
- `POST /api/discovery/decide {id, decision}` and `POST /api/discovery/batch {ids[], decision}` where `decision ∈ tracked|dismissed|tailoring|watch|skip`.

**Decision effects (handoff §D4):**
- `tracked` → create an `application` for the job at `stage='saved'`; set `job.discovery_decision='tracked'`. Leaves the queue (now in the tracker).
- `tailoring` → **create a run** for the job via `create_run()` (the hand-off) **and** create a tracked `application`; set `discovery_decision='tailoring'`. Return the run id / prompt so the UI can surface the manual hand-off. Leaves the queue.
- `dismissed` → `discovery_decision='dismissed'`. **Never resurfaces**; dedupe incoming jobs against dismissed (match on `url`, else `company`+`title`).
- `watch` → upsert the company into `watchlist`; `discovery_decision='watch'`.
- `skip` → `skipped_on = today`; stays undecided, drops from today's queue, returns tomorrow.

Membership (derive, never persist): `inQueue = decision is null and eligibility != 'ineligible' and freshness != 'closed' and skipped_on != today`; `inSetAside = decision is null and (eligibility == 'ineligible' or freshness == 'closed')`; order `closing(asc) → fit(strong<good<stretch) → postedDaysAgo(asc)`.

## 7. Resolved open questions (proposals — flag these for product)

- **Tailor hand-off (#9):** reuse `create_run()`; `tailoring` also tracks. Manual (no auto-runner). ✅ build this.
- **Today's queue sizing (#10):** cap at **20**, the top of the queue order; the rest are reachable in Browse. Make the cap a constant. *Flag for confirmation.*
- **Dismissed dedupe (#11):** `discovery_decision='dismissed'` + dedupe incoming on `url` then `company+title`. ✅
- **Scoring service (#8):** fit/eligibility/coverage come from `score_breakdown_json` (our scoring + eligibility judge). Reasons are whatever the judge stored; if absent, render the read without a reason rather than inventing one. The unclear/ineligible threshold is the judge's, not the UI's. *Generating fresh reasons for every role is a separate Claude-Code pipeline — out of scope here.*
- **Watchlist triggers (#12):** when a scored eligible role exists at a watched company, it appears in the queue normally; `watchlist.openRoles` reflects the count. No push notifications. ✅

## 8. Scope boundaries (do NOT build)

- The upstream **scoring/judging pipeline** (it exists; this build only *renders*
  what's in `score_breakdown_json`).
- **Sources** management and a **Runs/Activity** surface (not designed; separate).
- The **automated** tailor hand-off (stays the manual copy-prompt run model).
- Dark mode; virtualization; `closes_at`/`freshness` population (verify_open).

## 9. Verification (the gate — required before "done")

1. `cd frontend && npm run build` is green (tsc + vite).
2. **Pixel parity:** serve the built SPA and the prototype, screenshot both at
   1440×900 (Chrome headless, `--force-device-scale-factor=2`), and confirm the
   **Review queue, Browse, Watchlist, and the JD drawer are visually identical**
   to `designs/v1.1/Discovery.html`. Use the sample fixture so the data matches.
   Iterate until identical. (This is exactly how the tracker was verified — see
   the git history of `frontend/`.)
3. End-to-end on real data: `MATCHBOX_PROFILE=shiva` → `/discover` renders scored
   jobs; a decision persists and removes the role from the queue; `tailoring`
   creates a run.
4. `python3 -m pytest -q` stays green; add a `tests/test_discovery.py` (mirror
   `tests/test_tracker.py`) covering the serializer, membership rules, and the
   decision effects.
5. **Do not commit.** Leave the working tree on the current branch and report:
   what you built, the screenshot-parity result (with the image paths), test
   results, and any deviations or flags.

## 10. File map (new / changed)

**New:** `frontend/src/styles/discovery.css` · `frontend/src/discovery/**`
(types, dui, screens, DiscoveryApp, store, api, sample) ·
`src/matchbox/core/006_discovery.sql` · `src/matchbox/discovery_api/**`
(rules, repo, service) · `src/matchbox/web/routes/discovery.py` ·
`tests/test_discovery.py`.
**Changed:** `frontend/src/main.tsx` (path-based shell switch) ·
`src/matchbox/web/app.py` (serve `/discover`, include the discovery router) ·
`src/matchbox/web/templates/base.html.j2` (a "Discover" nav link, optional).
