# Matchbox v1 — Engineering spec

**From:** reasoning-engine planning pass · **Status:** ready to build · **Audience:** the engineer/agent who builds this (assume no prior context)

This spec works **backwards from the design team's approved dashboard** (`designs/v1/`) to everything that must change in the current codebase to bring it live, and frames it inside the larger product: a SOTA **job-discovery + CV-tailoring + application-tracking** tool, multi-user, with **Claude Code as the reasoning runtime**.

It reflects four locked product decisions:

1. **Stack:** port the dashboard to a bundled **React + TypeScript** SPA (not re-skin in HTMX).
2. **Data:** **hybrid DB** — one shared *discovery* DB + one *personal* DB per user, switchable live from the UI.
3. **Runtime:** the **dashboard triggers Claude Code runs** (no more manual copy-paste of a prompt).
4. **Themes:** CVs keep their **own** design system (not the app's "Oat" brand) and gain a **theme registry**.
   v1 **scope = tracker first**: the React+Oat app owns Today / Applications / Insights / Detail; discovery and tailoring stay on the current Jinja pages and migrate to Oat later.

---

## 0. Current state (verified ground truth)

So the executor does not re-discover it.

**Stack today:** FastAPI + Jinja2 templates + HTMX + Tailwind (CDN). **No JS build step, no `package.json`, no Node.** Fonts self-hosted at `src/matchbox/web/static/fonts` (IBM Plex). App assembled in `src/matchbox/web/app.py`; 9 flat routers (`applications, inbox, library, onboarding, profile, review, review_run, sources, targets`) — every endpoint returns HTML or HTMX fragments.

**DB today:** SQLite, **one file per profile** at `people/<slug>/matchbox.db`. Path resolved by `db_path(profile)` in `src/matchbox/core/db.py`; profile chosen by the `MATCHBOX_PROFILE` env var (default `demo`) **at process start** — not switchable at runtime. `MATCHBOX_DB` overrides the path. `get_conn()` in `src/matchbox/web/deps.py` opens a **fresh connection per request** and runs `migrate()` lazily. Migrations are version-tracked in a `migration` table by `src/matchbox/core/migrations.py`; current files: `schema.sql` (v1), `002_graph.sql` (v2), `003_job_geo.sql` (v3), `004_application_tracking.sql` (v4). **Adding v5+ is clean.**

**Profiles today:** no registry — just folders (`people/demo`, `people/livefire`, `people/shiva`). No code lists them. Created by hand. Each holds `matchbox.db`, `output/<run-id>/<job-id>/…`, `bases/`, and user YAML.

**Tailoring run model today (manual):** user selects jobs in `/inbox` → `POST /runs` → `create_run()` (`src/matchbox/scoring/runs.py`) writes `runs/<run-id>/work-queue.json` (validated vs `schemas/work-queue.v1.json`) + `run`/`run_job` rows. The UI then shows a **copyable prompt** "process run `<id>`"; the user pastes it into a **Claude Code terminal**; the brain runs CLIs (`matchbox-jobreqs`, `matchbox-assemble`) and writes `runs/<run-id>/status.json` (vs `schemas/status.v1.json`); the app polls `/review-run/<id>`. **No background queue, no programmatic Claude invocation.**

**Render/themes today:** `assemble.py::_render_pdf` → `render_html.render_cv_pdf` (HTML→weasyprint, the current path). ⚠️ **`render_html.cv_json_to_html` accepts `palette`/`font` but ignores them** — the look is hardcoded (IBM Plex + zinc). The **Typst** template (`src/matchbox/templates/typst/cv.typ`) *does* implement 5 palettes + 4 fonts via `--input`, and `schemas/work-queue.v1.json` + the `run_job` table already carry `palette`/`font` per job — but the HTML path we shipped this session dropped that.

**⚠️ Uncommitted:** the `funded_company` table exists in the live DB (built this session by `scripts/funded_companies.py`, its own DDL) but is **not** in any tracked migration. Must be formalized (→ shared discovery DB, §5).

**The design (`designs/v1/`):** React 18 prototype (CDN React + in-browser Babel; **port to bundled React+TS**). "Oat" system — Hanken Grotesk + JetBrains Mono, zinc neutrals + taupe `--oat-600 #574747`, 6px radius, 1px borders, `light-dark()` tokens, matchstick logo, Lucide icons, **no chart lib** (hand-built CSS viz). Four surfaces (Today / Applications / Detail drawer / Insights), a single `useApps()` store with an **8-action contract** (each action mutates + appends a timeline event + toasts), and a richer data model than we persist today. `tweaks-panel.jsx` is a **design-time tool — exclude**.

---

## 1. Target architecture

```
                         ┌──────────────────────────────────────────────┐
                         │   FastAPI (localhost, single process)         │
   Browser               │                                              │
 ┌──────────┐  JSON/SSE  │  ┌────────────┐   ┌─────────────────────┐    │
 │ React SPA │◀──────────┼─▶│  /api/*    │   │  Jinja pages (kept)  │    │
 │  (Oat)    │           │  │  tracker,  │   │  inbox, library,     │    │
 │ Today/    │  static   │  │  users,    │   │  review, sources,    │    │
 │ Tracker/  │◀──────────┼──│  runs      │   │  targets, onboarding │    │
 │ Detail/   │           │  └─────┬──────┘   └─────────────────────┘    │
 │ Insights  │           │        │                                     │
 └──────────┘           │   ┌────▼───────────┐   ┌──────────────────┐  │
                         │   │  Repository /  │   │  AgentRunner      │  │
                         │   │  DAL (per-req  │   │  (headless Claude │  │
                         │   │  profile)      │   │   Code subprocess)│  │
                         │   └────┬───────┬───┘   └────────┬─────────┘  │
                         └────────┼───────┼────────────────┼────────────┘
                                  │       │                │ work-queue.json / status.json
                      ATTACH      ▼       ▼                ▼ (unchanged file contract)
            people/_shared/discovery.db   people/<user>/matchbox.db   claude -p "process run X"
            (ats_source, job postings,    (library, runs, applications  → matchbox-jobreqs / -assemble
             funded_company)               + notes/contacts/events,      → writes status.json
                                           per-user job_state/score)
```

Three pillars on this spine: **Discovery** (global pool), **Tailoring** (per-user, Claude-driven), **Tracking** (per-user, the Oat SPA). The brain is **Claude Code**, invoked headless by the AgentRunner using the **same file contract** that works today.

---

## 2. Gap analysis — working backwards from the dashboard

For each thing the design needs, what exists, and what's missing.

| # | Design needs | Today | Gap / work |
|---|---|---|---|
| G1 | A React+TS SPA, bundled, with Hanken/JetBrains/Lucide | No bundler at all | Add **Vite + TS**; self-host both fonts; bundle `lucide-react`; FastAPI serves the build (§8) |
| G2 | `Application` with `salary, source, starred, hasDraft, nextAction{kind,label,due,time}`, **notes[]**, **contacts[]**, **events[]** timeline, stages `saved/applied/phone/onsite/offer/rejected` | `application` has flat `status (draft…withdrawn)`, single `notes` text, no salary/source/star/draft, no contacts/events | **Migration v5** (§4): expand `application`, add `note`/`contact`/`event` tables, **remap stages** |
| G3 | JSON read + 8 mutating actions, each writing a timeline event | Endpoints return **HTML fragments** | New **`/api/*` JSON layer** (§6) mirroring the `useApps()` contract |
| G4 | Switch users from inside the dashboard | Profile fixed by env var at startup | **Profile registry + request-scoped profile + switch endpoint** (§3) |
| G5 | "Discover once, shared" + per-user privacy | One DB per profile; discovery (`job`, `ats_source`, `funded_company`) duplicated per profile | **Hybrid DB via ATTACH** (§5); split `job` posting (global) from per-user `job_state` |
| G6 | "Tailor this" / runs kicked off from the UI | Manual copy-paste prompt into a terminal | **AgentRunner** — headless `claude -p` triggered by `POST /api/runs` (§7) |
| G7 | A "saved" stage = roles pulled into the pipeline before applying | `application` rows are created at tailor/apply time only | **Save-a-job → create pipeline row at `stage='saved'`** (the discovery↔tracking bridge, §9) |
| G8 | `hasDraft`, "Send", document links in Detail | We already produce `cv_path`/`cover_path` per application | **Map** `hasDraft` ← a tailored cover/CV exists; "Send" ← mark-sent; link `cv_path`/`cover_path` into Detail (§9) |
| G9 | CV theme variety | HTML renderer ignores palette/font (dead); themes only in Typst | **Theme registry** in the HTML renderer (§10) |
| G10 | Empty/first-run/loading/error states, add-application form | Not designed, not built | **v1 polish phase** (§11) |

---

## 3. Multi-user: profile registry + live switching

Smallest correct change to make the env-bound profile switchable per request.

1. **Registry.** Add a lightweight registry of users. Two options — pick (a) for v1:
   * **(a)** Scan `people/*/` for dirs containing `matchbox.db`; each is a user. A `people/_shared/` dir is reserved (not a user). Display name from that DB's `profile.full_name`.
   * (b) A `people/_users.json` manifest. More explicit; do later if (a) gets noisy.
2. **Active profile per request.** Stop reading `MATCHBOX_PROFILE` in the request path. Store the active user in a **signed cookie / session** (`mb_user`). Add middleware that sets `request.state.profile = cookie or default`.
3. **Connection dep.** Rewrite `get_conn()` (`web/deps.py`) to resolve `db_path(request.state.profile)` and (later, §5) `ATTACH` the shared DB. Keep per-request open/migrate/close.
4. **Endpoints.** `GET /api/users` → `[{slug, name, isActive}]`; `POST /api/users/switch {slug}` → set cookie, 200; (optional) `POST /api/users {name}` → scaffold `people/<slug>/` + migrate a fresh DB. The Oat sidebar footer "user chip" drives these.
5. **CLI parity.** All `matchbox-*` CLIs already accept `--db`; the AgentRunner (§7) passes the active user's DB path explicitly so headless runs hit the right DB.

> Output folders stay per-user: `people/<slug>/output/<run-id>/<job-id>/…`. Nothing about outputs changes.

---

## 4. Data-model migration (v5) — the pipeline model

Evolve `application` into the design's richer per-user "pipeline item." **Per-user DB only.**

**Stage remap** (data migration, in v5):

| Current `application.status` | New `stage` |
|---|---|
| `draft` | `saved` |
| `applied` | `applied` |
| `interview` | `phone` *(design splits phone/onsite; cannot auto-split → default `phone`)* |
| `offer` | `offer` |
| `rejected` / `withdrawn` | `rejected` *(label "Closed", reopenable)* |

**Schema (v5):**

```sql
-- expand the pipeline row
ALTER TABLE application ADD COLUMN stage TEXT;             -- backfilled from status per map above
ALTER TABLE application ADD COLUMN salary TEXT;            -- display string
ALTER TABLE application ADD COLUMN source TEXT;            -- "Referral · Dana", "Greenhouse", …
ALTER TABLE application ADD COLUMN starred INTEGER NOT NULL DEFAULT 0;
ALTER TABLE application ADD COLUMN has_draft INTEGER NOT NULL DEFAULT 0;
ALTER TABLE application ADD COLUMN updated_at TEXT;        -- drives staleness; set on every mutation
ALTER TABLE application ADD COLUMN next_action_kind TEXT;  -- apply|followup|interview|prep|thanks|offer|wait
ALTER TABLE application ADD COLUMN next_action_at  TEXT;   -- already exists; keep (the "due" date)
ALTER TABLE application ADD COLUMN next_action_time TEXT;  -- "13:30" for interviews
-- next_action (label) already exists. response_type/response_at already exist.

CREATE TABLE app_note (
  id INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE app_contact (
  id INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
  name TEXT NOT NULL, role TEXT, initials TEXT
);
CREATE TABLE app_event (   -- the history timeline; every action appends one
  id INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES application(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,      -- saved|applied|reply|screen|onsite|offer|rejected|note|advanced|followup
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
```
* Keep the old `status`/`notes` columns through v5 for rollback safety; drop in a later migration once the SPA is the only writer.
* **Derive, never persist:** `stale`, due-buckets, Today selection, monogram colors — computed exactly as the prototype does (porting `data.js`/`ui.jsx` logic to the client or a shared util). Production stores **ISO timestamps**; the API derives `daysAgo` (or the client does).
* **Business rules** to port verbatim from the handoff §07: `FLOW`, `isStale` (active stage ∧ no action due ≤3 ∧ `updated ≥ 11d`), due buckets, Today ranking. Put them in **one shared module** reused by API and client so they cannot drift.

---

## 5. Hybrid DB (shared discovery + per-user)

**Goal:** discovery mined once, shared; personal data private per user. SQLite cannot FK across files → use **`ATTACH DATABASE`** + soft references.

**Shared DB:** `people/_shared/discovery.db`. **Moves here:** `ats_source`, `funded_company` (formalize its DDL into this migration — fixes the uncommitted-table ALERT), and the **global job posting** fields of `job` (`company, title, location, url, apply_url, jd_text, requirements_json, requirements_model, requirements_jd_hash, posted_at, fetched_at, country, remote, source`).

**Per-user DB:** everything else — `profile, target`, the library (`experience, bullet, project, skill, summary_variant, claim, rendering, evidence, tag, item_tag, embedding`), `run`, `run_job`, the expanded `application` (+ `app_note/contact/event`), `setting`, and a **new per-user** `job_state`:

```sql
CREATE TABLE job_state (        -- per-user view of a shared job posting
  job_id INTEGER NOT NULL,      -- soft ref → discovery.db.job.id (no cross-file FK)
  status TEXT NOT NULL DEFAULT 'new',   -- new|scored|selected|tailored|applied|skipped|rejected
  score REAL,
  score_breakdown_json TEXT,    -- the per-user eligibility verdict
  PRIMARY KEY (job_id)
);
```

**Mechanism:** in `get_conn()`, after opening the per-user DB, run `ATTACH DATABASE '…/discovery.db' AS disc;` then query joins as `application … JOIN disc.job …`. Wrap all reads/writes in a **repository layer (DAL)** so call-sites do not hardcode which DB a table lives in — this is what lets §4/§5 land in either order without breaking the tracker.

**Phasing note:** the tracker (§8) can ship reading `job` from the **per-user** DB first; the discovery split is a later phase that repoints the DAL to `disc.job`. Sequence in §12.

---

## 6. JSON API (mirrors the `useApps()` contract)

New `src/matchbox/web/routes/api.py` (prefix `/api`). Returns JSON, not HTML. Active user from `request.state.profile`.

**Reads**
* `GET /api/applications` → `Application[]` (joined posting + pipeline + notes/contacts/events, ISO dates). Client derives `stale`/Today/Insights per the shared rules module.
* `GET /api/profile` → `{name, initials}` for the greeting + user chip.
* `GET /api/users`, `POST /api/users/switch` (§3).

**Mutations — one per store action (handoff §06). Each: update row, set `updated_at=now`, append an `app_event`, return the updated `Application`.**

```
POST /api/applications/{id}/advance            advanceStage → next in FLOW
POST /api/applications/{id}/stage   {stage}    setStage (incl. close/reopen)
POST /api/applications/{id}/snooze  {days=2}    push the action's due out
POST /api/applications/{id}/remind  {days}      set/replace due (0 = today)
POST /api/applications/{id}/done                markDone (clears hasDraft; apply→applied; sent→waiting)
POST /api/applications/{id}/response {type}     reply|rejected|ghosted (effects per §06 table)
POST /api/applications/{id}/note    {text}      addNote
POST /api/applications/{id}/star                toggleStar
POST /api/applications        {jobId}           save a discovered job → new row at stage 'saved' (G7)
```

**Runs (§7):** `POST /api/runs {jobIds, wantCover, theme}`, `GET /api/runs/{id}`, `GET /api/runs/{id}/events` (SSE).

> Keep the existing HTMX `/applications/*` routes until the SPA fully replaces them, then delete the interim grouped-list we built this session.

---

## 7. AgentRunner — dashboard-triggered Claude Code

The largest net-new backend piece. Removes the manual copy-paste while **preserving the file contract** (`work-queue.json` → CLIs → `status.json`).

**Flow:**

1. `POST /api/runs` → existing `create_run()` writes `work-queue.json` + `run`/`run_job` rows (status `queued`). Persist the **theme** alongside `palette/font` (§10).
2. **AgentRunner** (new `src/matchbox/agent/runner.py`) picks it up and spawns Claude Code **headless**:

   ```
   claude -p "process run <run-id>"  \
     --output-format stream-json --permission-mode acceptEdits \
     --add-dir <project_root>
   # env: ANTHROPIC_API_KEY (BYOK), MATCHBOX_DB=people/<user>/matchbox.db
   ```

   (Alternative: embed the **Claude Agent SDK** in-process instead of shelling out. Recommend the `claude -p` subprocess for v1 — literally "runs using Claude Code," least coupling.)
3. The headless agent reads `work-queue.json`, runs `matchbox-jobreqs` / `matchbox-assemble`, writes `status.json` — **unchanged**.
4. The runner tails `status.json` (and/or the stream), updates `run.status`, and streams progress to the SPA via **SSE** `GET /api/runs/{id}/events`; the Today/Tracker show live run state.

**Must address (call out in PR):**
* **BYOK key** management (a `setting` row or env); fail clearly if absent.
* **Permissions/sandbox** — headless Claude runs tools unattended. Scope `--allowedTools` to the matchbox CLIs + file writes under `runs/`; avoid blanket `--dangerously-skip-permissions`. This is a **security surface** — review before merge.
* **Single-flight queue** — one run at a time per process; queue the rest; surface `queued|running|done|error`.
* **Crash handling** — subprocess non-zero → `run.status='error'`, message to UI.

---

## 8. Frontend: build, serve, port

* **Toolchain:** add `frontend/` with **Vite + React 18 + TS**. Self-host **Hanken Grotesk** + **JetBrains Mono** (download to `static/fonts`, `@font-face`; no runtime Google-Fonts CDN — this is local-first). Bundle **`lucide-react`** (drop the CDN global). Import `colors_and_type.css` + `mb.css` as-is (they're plain CSS, no deps).
* **Serve from FastAPI:** build to `src/matchbox/web/static/app/`; mount; add a catch-all that returns `index.html` for SPA routes (`/`, `/today`, `/applications`, `/insights`) while `/api/*`, `/static/*`, and the kept Jinja pages (`/inbox`, `/library`, …) resolve normally. Reconcile nav: the Oat sidebar links to SPA routes; a "More" group links out to the Jinja pages until they migrate.
* **Port (mostly wiring, not redesign):** `App` shell (sidebar/routing/toast/prefs) · `Today` + `TaskRow` · `Tracker` + `PipeBar`/`Funnel` + `ListView`/`Row` + `BoardView`/`BoardCard` · `Detail` drawer (proper `role="dialog"`, focus trap) · `Insights` · atoms (`Icon, MonoLogo, StageDot, Due, Badge, StageStepper`, `QuickMenu`). Replace the prototype's in-memory `useApps()` with a hook that calls `/api/*` and refetches/optimistically updates. **Exclude `tweaks-panel.jsx`.** Ship **`direction='ledger'`** default; `focus` behind a pref; **drop `accent: forest|slate`** (only `taupe` is implemented in the CSS) or implement them — your call, flag in PR.
* **A11y to honor from handoff §12:** keyboard-reachable row actions (not hover-only), visible focus ring, due/stage never color-only, ≥40px hit targets, `prefers-reduced-motion`.

---

## 9. Concept mapping (matchbox ↔ design)

| Design | Matchbox |
|---|---|
| `Application` from `saved` onward | join(`application` pipeline row, `disc.job` posting). Saving a discovered job creates the row at `stage='saved'` (G7) |
| `stage` | remapped `application.stage` (§4) |
| `source` | `disc.job` source / referral string |
| `salary` | new `application.salary` (display string; we don't parse comp) |
| `hasDraft` | a tailored cover/CV exists for this application (`cover_path`/`cv_path` present) |
| "Send" / `markDone` on a draft | **mark-sent** (matchbox never sends email); clears `has_draft`, appends event |
| Detail documents | link `cv_path` / `cover_path` (served by the existing `/runs/<id>/output/...` route) |
| `events[]` history | `app_event` rows (§4) |
| `nextAction.kind` | `application.next_action_kind` |

---

## 10. CV theme registry (CVs keep their own brand)

Revive themeability in the **HTML/weasyprint** path (the one we ship), modelled on v0.3's Typst palettes.

* **Registry:** `src/matchbox/themes/` — one file per theme: `{ id, label, fonts: {sans, mono|serif, files}, tokens: {page, body, heading, muted, accent, hairline}, css? }`. Seed with the **current Plex/zinc** as default `ibm-plex`, plus v0.3's **slate / ink / forest / claret / bronze** (port the hexes from `templates/typst/cv.typ`). CVs are **not** the Oat brand — themes are CV-specific.
* **Renderer:** rewrite `cv_json_to_html(cv, *, theme)` so `cv.html` uses **CSS custom properties** injected from the theme (font `@font-face` + token values), instead of hardcoded values. Keep ATS-safety (single column, real text, ≤0.04em letter-spacing on headers, embedded fonts).
* **Selection:** `run_job` already stores `palette`/`font`; generalize to a single `theme` (keep `palette`/`font` as fallbacks). `schemas/work-queue.v1.json` already carries them — extend the enum or add `theme`. Surface a theme picker in the tailor flow (inbox/review-run today; the Oat tailoring screens later).
* **Fonts:** themes reference files in `shared/fonts`; bundle any new ones (e.g. Charter/Atkinson) or map to installed equivalents.

---

## 11. Scope gaps (v1 polish phase) & out-of-scope

Designers flagged as **not built** (handoff §11/§15) — schedule, don't assume:
* **Add / import application** form (manual + paste-URL parse). Top of funnel; bridges discovery → `saved`.
* **First-run (zero apps) / loading / error** states for every surface.
* **Dark mode** — tokens support `light-dark()` but screens weren't designed dark; schedule a dark pass if it ships.
* **Board drag-and-drop** between stages — not built; decide if v1.
* **List virtualization** — only if a user exceeds a few hundred rows.
* **Reminders/notifications** — in-app only for v1, or OS notifications? (handoff open-Q #3.)

---

## 12. Phasing (each milestone ships something)

* **P0 — Foundations.** Vite+TS toolchain; Oat tokens/fonts/logo; empty SPA mounted + served by FastAPI; `/api` skeleton; **multi-user switching** (§3). *Ships: switch users, see the Oat shell.*
* **P1 — Data model.** Migration **v5** (§4): expand `application`, add `app_note/contact/event`, stage remap + backfill; shared rules module. *Ships: data ready.*
* **P2 — Tracker SPA.** Port the four surfaces wired to `/api` + the 8 actions; concept mapping (§9). *Ships: the design, live — replaces the interim `/applications`.*
* **P3 — AgentRunner.** Headless `claude -p` triggered by `POST /api/runs`; SSE progress; "Tailor this" from the UI (§7). *Ships: dashboard-triggered tailoring.*
* **P4 — Theme registry.** Make the HTML renderer themeable; port v0.3 palettes + Plex default (§10). *Ships: CV themes.*
* **P5 — Hybrid discovery DB.** Split `job` posting → `people/_shared/discovery.db`; `ATTACH`; per-user `job_state`; formalize `funded_company` migration (§5). *Ships: discover-once, shared.*
* **P6 — Polish/gaps.** Add-application form, first-run/empty/error states, a11y hit-targets; optional dark/DnD/virtualization (§11).

**The design team's dashboard is live at P2; automation at P3.** P5 (DB split) is decoupled behind the DAL so it can slot before or after P3/P4 without breaking the tracker.

---

## 13. Risks / decisions to confirm before building

1. **AgentRunner permissions** — auto-running Claude Code with tool access is the main security surface. Lock `--allowedTools` to matchbox CLIs + `runs/` writes. (§7)
2. **`funded_company`** — currently outside migrations; fold into the P5 shared-DB migration; until then it is unversioned. (§5)
3. **Theme work is real** — the shipped HTML renderer ignores palette/font; reviving themes is renderer surgery, not a dropdown. (§10)
4. **Cross-DB integrity** — no FK across SQLite files; `job_state.job_id` is a soft ref. Add a periodic integrity check / cascade-on-read. (§5)
5. **Two frontend paradigms coexist** (React SPA + Jinja pages) until discovery/tailoring migrate to Oat — acceptable for "tracker first," but keep the nav bridge clean. (§8)
6. **`focus` direction + `forest/slate` accents** — ship `ledger`+`taupe` only for v1 unless you want the extra prefs. (§8)

---

## 14. File map (new / changed)

**New:** `frontend/` (Vite+TS, ported components) · `src/matchbox/web/routes/api.py` · `src/matchbox/agent/runner.py` · `src/matchbox/core/005_pipeline.sql` (+ `006_discovery_split.sql` for P5) · `src/matchbox/rules/` (shared FLOW/staleness/today) · `src/matchbox/themes/` (theme registry) · `people/_shared/discovery.db` (P5).
**Changed:** `web/app.py` (mount SPA + catch-all) · `web/deps.py` (request-scoped profile + ATTACH) · `core/db.py` (profile registry, dual-DB paths) · `render_html.py` + `templates/html/cv.html` (themeable) · `scoring/runs.py` (theme field, enqueue → AgentRunner) · `schemas/work-queue.v1.json` (theme) · delete interim `applications/` HTMX templates after P2.
