# Live-fire walkthrough

This is the record of the end-to-end verification run before v0.3 was
declared testable. It is also a working example a real user can copy.
Every artifact under `docs/examples/livefire-*` was used in this run.

## Setup

```bash
git clone https://github.com/5h1vmani/matchbox.git
cd matchbox
pip install -e ".[dev]"
brew install typst        # macOS; see typst docs for other platforms
export MATCHBOX_PROFILE=livefire    # isolates this run from people/demo
matchbox-web              # http://127.0.0.1:8765
```

Open `http://127.0.0.1:8765/` in a browser. With an empty profile the
root path redirects to `/onboarding`.

## Step 1 — onboarding

Copy the sample CV into `inbox/`:

```bash
cp docs/examples/livefire-sample-cv.md inbox/
```

In a real session you would drop your own CVs via the drag-and-drop
on `/onboarding` and then start Claude Code and paste `ingest my files`.
For the walkthrough we skip Claude Code and use the pre-built payload:

```bash
MATCHBOX_PROFILE=livefire matchbox-ingest \
  --file docs/examples/livefire-ingest.json
```

Result: `Riley Chen` profile, 2 experiences, 6 unverified bullets,
6 skills, 9 tags, 1 summary variant. All bullets land with
`facts_verified=false`.

## Step 2 — review and confirm

Open `/review`. Read each bullet. Use the per-experience "Verify all"
button, or the global "Verify all unverified" at the top, to flip
every bullet to verified.

## Step 3 — targets

Open `/targets`. For the walkthrough we set:

* Role families: `forward-deployed-engineer, ml-platform-engineer`
* Dream companies: `Anthropic, Modal`
* Locations: `remote`
* Comp: 180000 to 260000 USD
* Exclusions: `defense, gambling`

## Step 4 — sources

Open `/sources`. Add `greenhouse` / `anthropic` / `Anthropic` as the
display name. Click "Test the slug" to verify (this hits the live
Greenhouse endpoint). For the walkthrough we inserted two jobs
directly into the DB instead of running a real scan; M3 has 15 tests
covering the polling path.

## Step 5 — score and triage

`/inbox` shows both jobs. Click "Score new jobs". The deterministic
5-dimension rubric runs. With this profile both jobs score 0.81 —
strong fit. Per-row Skip / Reject / Re-open works for jobs you do
not want to apply to.

Tick the CV checkbox for the Forward Deployed Engineer job, leave
cover off, pick palette `slate` and font `source-serif`, click
"Start tailoring".

The app writes `runs/<run-id>/work-queue.json` validated against
`schemas/work-queue.v1.json`.

## Step 6 — process the run (the brain side)

In a real session you would paste `process run <id>` into Claude
Code. For the walkthrough we drive the CLIs by hand. First, save
the extracted JD requirements (the brain would produce this from the
JD text):

```bash
MATCHBOX_PROFILE=livefire matchbox-jobreqs save --job 1 \
  --file docs/examples/livefire-job1-requirements.json
```

Then assemble the CV:

```bash
MATCHBOX_PROFILE=livefire matchbox-assemble --run 2026-05-22-001 --job 1
```

On first run this downloads `BAAI/bge-small-en-v1.5` (~30 MB) via
fastembed. Subsequent runs use the cached model.

The output lands under `runs/<run-id>/output/<job-id>/`:

* `cv.pdf` (~31 KB)
* `cv.json` (re-renderable structure with `_selected_bullets`
  fingerprints)
* `cv.typ` (local copy of the template — keeps the artifact dir
  self-contained)
* `coverage.json` (semantic coverage + ATS keyword presence)
* `changes.md` (per-experience Selected / Skipped, gaps, missing
  keywords with polish candidates)

For the walkthrough: all 3 must-haves are semantically covered
(cosine ≥ 0.5 against the real bge embeddings), all 3 keywords are
literally present in the rendered text.

## Step 7 — optional polish pass

The matcher selected the right bullets but the wording could be
sharpened. The brain proposes a rephrase that includes an explicit
"operated" verb and "production" qualifier (truthful — both apply):

```bash
MATCHBOX_PROFILE=livefire matchbox-assemble --run 2026-05-22-001 --job 1 \
  --polish docs/examples/livefire-job1-polish.json
```

`polish: applied 1, rejected 0`. The PDF is re-rendered with the new
wording, the old text is gone from the extracted PDF text, and
`changes.md` gains a `## Polished` section showing was/now per bullet.

## Step 8 — review run and apply

`/review-run/2026-05-22-001` polls `status.json` and renders one card
per job. The card embeds the PDF, links to `changes.md` ("What
changed"), shows any drift warning if the underlying library bullets
have been edited since this render, exposes a palette/font restyle
control, and surfaces an Apply ↗ button plus a Mark applied form.

`/runs` lists every run with Abandon (only while queued/running) and
Delete (clears the on-disk artifacts).

## What this run verified

* The web server boots and serves all expected routes.
* Empty profile redirects to /onboarding.
* The ingest path actually populates the DB with the right shape.
* /review surfaces unverified bullets and the global verify-all works.
* /targets persists the row.
* /sources accepts a new ATS source.
* Scoring runs and ranks jobs.
* Skip / Reject / Re-open move jobs between triage statuses.
* Starting a run writes a schema-valid work-queue.json and creates the
  run row + run_job links.
* `matchbox-jobreqs save` stores the requirements payload.
* `matchbox-assemble` with the **real fastembed embedder** produces a
  non-empty PDF, with all must-haves covered against the production
  semantic floor (0.5) and every JD keyword literally present.
* `coverage.json` and `changes.md` carry the expected sections.
* The sandboxed file server returns PDF and Markdown with the right
  content-types.
* Mark applied creates the application row and flips job.status.
* Restyle re-renders with a new palette/font and persists the choice.
* The polish pass replaces a selected bullet, re-renders the PDF,
  re-runs keyword presence, and appends a Polished section to
  changes.md.
* Abandon flips a run to error and frees its selected jobs back to
  scored.

## What this run found

One real bug: `pyproject.toml` had `dependencies = [...]` accidentally
sitting under `[project.urls]` instead of `[project]`. Hatchling's
new strict validation refused to install. Fixed in the same commit
as this walkthrough.

Otherwise the loop works end to end against the real embedder and
real Typst binary, with all 182 tests passing afterward.
