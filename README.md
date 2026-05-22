# Matchbox

[![CI](https://github.com/5h1vmani/matchbox/actions/workflows/ci.yml/badge.svg)](https://github.com/5h1vmani/matchbox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Type checked: mypy strict](https://img.shields.io/badge/type%20checked-mypy%20strict-2bbc8a.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/lint%20%2B%20format-ruff-261230.svg)](https://github.com/astral-sh/ruff)

> Local desktop app that turns your career history into a tagged library,
> scans ATS boards for matching roles, and assembles tailored CVs with
> Claude Code as the reasoning engine. Your data stays on your laptop.
> Matchbox holds no LLM credentials.

## How it works (v0.3)

Two halves joined by a file-based handoff:

* **The app** (this repo): SQLite, FastAPI + HTMX web UI, ATS pollers,
  deterministic scoring, Typst PDF rendering. Holds no LLM client.
* **The brain** ([Claude Code](https://claude.com/claude-code)): parses
  your old CVs, extracts JD requirements, polishes wording. Drives the
  CLIs (`matchbox-ingest`, `matchbox-jobreqs`, `matchbox-assemble`)
  through a versioned JSON contract in `runs/` and `schemas/`.

Selection (which bullets land on a given CV) is deterministic math, not
LLM judgement. The brain does only what is genuinely irreducible:
parsing messy input, extracting JD requirements, optional wording
polish.

## Prerequisites

* Python 3.12+
* [Typst](https://github.com/typst/typst) for PDF rendering:
  `brew install typst` (macOS) or download from the Typst releases.
* [Claude Code](https://claude.com/claude-code) installed and runnable
  from your terminal. The app never talks to an LLM API directly.

## Install

```bash
git clone https://github.com/5h1vmani/matchbox.git
cd matchbox
pip install -e ".[dev]"
```

The first time `matchbox-assemble` runs it downloads a ~30 MB ONNX
embedding model (`BAAI/bge-small-en-v1.5`) via `fastembed`.

## Quickstart (real flow, ~10 minutes)

```bash
matchbox-web                  # starts http://127.0.0.1:8765
```

Open the browser. Empty profile state lands you at **/onboarding**:

1. **Onboarding.** Drag in old CVs (PDF/DOCX), LinkedIn exports, plain
   text notes, anything that describes your work. Or paste freeform
   text. Files stage into `inbox/` on this machine.

2. **Run Claude Code on the staged files.** Open a terminal in the
   repo, start `claude` (or your Claude Code launcher), and paste the
   prompt the page shows you:

   ```text
   ingest my files
   ```

   The brain reads `inbox/`, extracts experiences and bullets and
   skills, writes them to your DB via `matchbox-ingest`. Rows land
   with `facts_verified = false`.

3. **Review.** Open `/review`. Read every bullet. Fix wording. Delete
   noise. Confirm what is true. Only confirmed bullets are eligible
   for CV tailoring.

4. **Targets.** `/targets`. Role families, dream companies, locations,
   exclusions.

5. **Sources.** `/sources`. Add a company by ATS type (Greenhouse,
   Lever, Ashby, SmartRecruiters, Recruitee) and slug. Click
   "Test the slug" before saving to verify the endpoint. Click
   "Scan all enabled" to fetch jobs. See
   [docs/supported-ats.md](docs/supported-ats.md) for live-verified
   example slugs per vendor. Workable is deferred — their public
   no-auth API was removed by the vendor.

6. **Triage.** `/inbox`. The five-dimension rubric scores every new
   job; click "Score new jobs" to refresh. Per row: Skip, Reject, or
   include in a tailoring run by ticking CV and/or cover. Pick palette
   and font for the run. Click "Start tailoring".

   Have a LinkedIn link or a JD that is not on a polled ATS? Expand
   **Add a job by hand** at the top of `/inbox`. Paste company, title,
   URL, and the full JD text. The row lands as `new` and goes through
   the same score / triage / tailor flow.

7. **Process the run.** A new `runs/<id>/work-queue.json` is on disk.
   Copy the prompt the page shows you, paste into Claude Code:

   ```text
   process run 2026-05-22-001
   ```

   The brain processes each job: extracts requirements via
   `matchbox-jobreqs`, runs `matchbox-assemble` to render the PDF,
   writes `status.json` as it progresses. The CV PDF, coverage report,
   and a `changes.md` diff land under `runs/<id>/output/<job>/`.

8. **Review run + apply.** `/review-run/<id>` polls `status.json` and
   shows each CV inline. The page surfaces uncovered must-haves, any
   ATS keyword misses, and (M7+) "Polish candidates" the brain can
   rephrase to carry missing keywords. When you click **Apply**, the
   job's apply URL opens in a new tab. **Mark applied** when you
   submit.

## Architecture (one screen)

```text
inbox/                  user drops files                        app stages
runs/<id>/              app writes work-queue.json              brain reads
                        brain writes status.json                app polls

people/<slug>/matchbox.db    one SQLite DB per profile
shared/rubric.json           deterministic 5-dimension scoring
shared/voice-rules.json      polish-pass guardrails
schemas/*.v1.json            JSON Schema contracts
src/matchbox/
  core/                      DB, models, library CRUD
  onboarding/                ingest CLI
  discovery/                 ATS pollers + scan runner
  scoring/                   rubric + run creation
  matching/                  embed, BM25, RRF, MMR, coverage
  polish.py                  voice-rules-validated keyword alignment
  templates/typst/           cv.typ + cover.typ
  web/                       FastAPI + HTMX routes + Jinja templates
  assemble.py                deterministic select + render orchestrator
  jobreqs.py                 brain's requirements writer
```

## Commands

```bash
matchbox-web                                          # web UI on 127.0.0.1:8765
matchbox-ingest --file payload.json                   # brain writes the library
matchbox-jobreqs save --job 42 --file reqs.json       # brain saves JD requirements
matchbox-assemble --run <run-id> --job 42             # select + render CV
matchbox-assemble --run <run-id> --job 42 --cover     # render cover letter
matchbox-assemble --run <run-id> --job 42 \
    --polish polish.json                              # apply the polish pass
```

CLAUDE.md at the repo root tells Claude Code how to drive these.

## Security

Single-user local tool. No auth. No CSRF. The web server binds to
`127.0.0.1` only (ADR-0005). Do not expose to the network. The PDF
serving route is sandboxed to `runs/<id>/output/<job-id>/` with
path-traversal guards.

## Documentation

* [Testing guide](docs/testing-guide.md) — step-by-step runbook for
  testers (shortcut + real flow)
* [Supported ATS](docs/supported-ats.md) — per-vendor live status with
  verified example slugs
* [v0.3 design](docs/v0.3-design.md) — the design document this build
  follows
* [Live-fire walkthrough](docs/examples/livefire-walkthrough.md) — the
  end-to-end verification record
* [Decision records](docs/decisions/) — durable architectural choices
* [Contributing](CONTRIBUTING.md)
* [Security policy](SECURITY.md)
* [Changelog](CHANGELOG.md)

Earlier versions of the docs (architecture, cli-reference, ux-design,
setup, troubleshooting, operator-runbook, index) lived under `docs/`.
They described v0.2 and now sit under `archive/v0.2/docs/`. v0.3
documentation is the README plus `docs/v0.3-design.md` plus this
section.

## License

MIT — see [LICENSE](LICENSE).
