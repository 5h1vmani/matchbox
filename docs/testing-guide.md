# Testing Matchbox

Two paths: the **shortcut** (uses committed fixtures, no Claude Code
needed; ~5 minutes) and the **real flow** (your own CV + Claude Code
drives the brain; ~10–15 minutes). Run the shortcut first to verify
the install. Then the real flow.

## Setup (both paths)

```bash
git clone <repo> matchbox
cd matchbox
pip install -e ".[dev]"                   # pulls in weasyprint (the PDF renderer)
brew install pango                        # macOS: weasyprint needs Pango/Cairo at runtime
                                          # Debian/Ubuntu: see .github/workflows/ci.yml's apt step
cd frontend && npm install && npm run build  # build the React SPA the server serves
cd ..
matchbox-web                             # http://127.0.0.1:8765
```

Open the browser at `http://127.0.0.1:8765`. The whole app is one React
SPA; with an empty profile it lands on the onboarding screen. Run a
sanity check:

```bash
python -m pytest -q                       # should report 326 passed, 3 skipped
```

## Shortcut (no Claude Code)

Run in a second terminal, with the web server still running.

```bash
export MATCHBOX_PROFILE=demo

# 1. Ingest a fixture CV (pretends Claude Code already parsed your files)
matchbox-ingest --file docs/examples/livefire-ingest.json

# 2. Confirm in the UI
#    In the SPA, open the Review screen and click "Verify all unverified"

# 3. Set targets
#    In the SPA, open the Profile screen (Targets live there now) and
#    fill role families, dream companies, locations.

# 4. Add a job by hand (the LinkedIn / non-polled-ATS path)
#    In the SPA, open the Inbox screen.
#    Expand "Add a job by hand" and paste any real LinkedIn JD, or use
#    this synthetic one:
#       company: Anthropic
#       title:   Forward Deployed Engineer
#       url:     https://example.com/test-fde
#       jd_text: We need someone to build ETL pipelines, operate
#                Kubernetes clusters in production, and mentor engineers.
#                Strong Python required.

# 5. Score
#    Click "Score new jobs". The job ranks at the top of the inbox.

# 6. Start a tailoring run
#    Tick CV for the job, pick palette + font, click "Start tailoring".
#    Note the run id shown (e.g. 2026-MM-DD-001).

# 7. Simulate the brain by hand (fixtures provided)
matchbox-jobreqs save --job <job_id> --file docs/examples/livefire-job1-requirements.json
matchbox-assemble --run <run_id> --job <job_id>

# 8. Open the result
open runs/<run_id>/output/<job_id>/cv.pdf
#    Then open the Run review screen for <run_id> in the SPA.
```

**Pass criteria**: a non-empty CV PDF (~30 KB) whose extracted text
contains "kubernetes", "pipelines", and "python". `coverage.json`
under the same dir reports `"covered": true` for every must-have at
the production semantic floor (0.5).

## Real flow (your own CV + Claude Code)

```bash
export MATCHBOX_PROFILE=$(whoami)
matchbox-web                             # leave this running
```

The AI engine is a manual handoff: there is no headless runner. The app
writes typed intents to an agent-task queue plus `runs/<id>/work-queue.json`
and surfaces a copyable `process run <id>` prompt. In a second terminal
start Claude Code (`claude`) and drive each step by pasting the prompt the
SPA shows you; Claude Code drains the queue and runs `matchbox-assemble`.
The interesting touch points (each is a screen in the SPA at
`http://127.0.0.1:8765`), in order:

1. **Onboarding screen** — drag your old CVs / LinkedIn export / notes.
   Paste `ingest my files` into Claude Code. It will read `inbox/`,
   extract structured data, and write rows via `matchbox-ingest`.

2. **Review screen** — every bullet starts unverified. Read each one,
   fix anything that is wrong, delete noise. Hit "Verify all
   unverified" when you trust the lot. Per-bullet edit-in-place is
   on hover.

3. **Profile screen** — fix anything the brain missed: typos, missing
   email, links. Targets live here too: what you are looking for —
   role families, dream companies, locations, exclusions.

4. **Sources screen** — add a real ATS source. Live-verified slugs (as
   of 2026-05-22, see `docs/supported-ats.md`):
   * `greenhouse / anthropic` → 392 jobs
   * `lever / palantir` → 222 jobs
   * `ashby / linear` → 23 jobs
   * `smartrecruiters / Visa` → 20 jobs (case-sensitive)
   * `recruitee / bunq` → 34 jobs

   Click **Test the slug** before saving. Then **Scan all enabled**.

   Have a LinkedIn link or a job from a non-polled vendor? Use
   **Add a job by hand** on the Inbox screen (see step 5).

5. **Inbox screen** — scanned jobs ranked by the 5-dimension rubric. Per
   row: Skip (not now), Reject (no), or include in a run. The **Add
   a job by hand** card lets you paste a JD URL + JD text for jobs
   that did not come from a poller.

6. **Start tailoring** — pick palette/font, tick CV / cover per row,
   click Start. Paste `process run <id>` into Claude Code.

7. **Run review screen** — polls `status.json`. Each card embeds the
   rendered PDF. "What changed" links to the per-job `changes.md`
   (selected/skipped diff, gaps, ATS keyword misses with polish
   candidates). Apply ↗ opens the JD's apply URL; **Mark applied**
   records it.

8. **Runs screen** — Abandon a stuck run (only while queued/running),
   Delete a finished one (also clears the on-disk PDFs).

## What to look for / common failures

* **First `matchbox-assemble` hangs ~15 seconds.** `fastembed` is
  downloading `BAAI/bge-small-en-v1.5` (~30 MB). Only happens once.
  Cached under `~/.cache/fastembed/`.
* **weasyprint can't find Pango/Cairo.** The renderer imports
  `weasyprint`, which needs the system Pango/Cairo libraries at runtime.
  macOS: `brew install pango`. Debian/Ubuntu: the libpango/libcairo
  packages (see `.github/workflows/ci.yml`'s apt step).
* **Sources scan returns 404.** The slug is wrong or the company
  moved off that ATS. `docs/supported-ats.md` has verified examples.
* **Brain wrote a bad `status.json`.** The review-run page renders
  anyway with a warning banner listing the schema errors. Fix the
  brain output; the next poll picks up the corrected file.
* **CV PDF is missing keywords.** Check "What changed" — the "ATS
  keyword misses" section lists which terms are absent and which
  selected bullets could carry them. Run the polish pass:
  `matchbox-assemble --run <id> --job <job> --polish polish.json`.
* **Edited a library bullet after rendering a CV?** The run-card
  surfaces a "cv.json may be stale" warning. Re-tailor to pick up
  the edit.
* **The brain produced wrong output.** The schemas under `schemas/`
  are the contract. If validation fails, the error message points at
  the exact field. See `CLAUDE.md` for the brain's instructions.

## Where to file issues

* **Code bugs.** The live-fire pass found one (`pyproject.toml`
  install bug). Run `python -m pytest tests/ -q` to confirm tests
  still pass before reporting. Include the OS, Python version, and
  the failing command's stderr.
* **Vendor drift** (an ATS endpoint stops returning 200). Update
  `docs/supported-ats.md` with the new verified slug or mark the
  vendor deferred. The poller often does not need changes.
* **UI confusion.** Copy lives in `frontend/src/` now (the legacy
  Jinja pages are archived under `archive/jinja/`). The voice rules
  are at `shared/voice-rules.json`.
* **Brain not following CLAUDE.md.** The schemas under `schemas/`
  validate the brain's output. The page surfaces validation errors;
  the brain side is a prompt issue, not a code issue.

## Health checks you can run any time

```bash
# Deterministic side
python -m pytest tests/ -q

# Real embedder (opt-in, ~15s on cache hit, longer on first run)
MATCHBOX_FASTEMBED_TEST=1 python -m pytest tests/test_fastembed_integration.py -v

# Boot the app and curl the root
matchbox-web &
sleep 2 && curl -sS http://127.0.0.1:8765/healthz
```
