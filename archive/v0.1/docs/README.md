# Matchbox Docs

Practical guides for running the Matchbox job-search pipeline.

## What Matchbox is (one paragraph)

Matchbox is a personal job pipeline. It scans job boards across 8 countries (India, US, UK, Singapore, EU, Australia, Canada, New Zealand), scores each role against your profile, stores everything in a SQLite database, and lets you review via a Streamlit UI. When you pick jobs to pursue, Matchbox tailors a CV (and optional cover letter) using your identity data from Atma. You submit manually via each company's portal; Matchbox tracks state through the pipeline from `evaluated` to `offer`.

## Read these in order

| # | Doc | When to read |
|---|-----|--------------|
| 1 | [setup.md](setup.md) | First time only. Install dependencies, verify DB, run your first scan. |
| 2 | [operator-runbook.md](operator-runbook.md) | Every time you use the system. The daily workflow. |
| 3 | [commands-reference.md](commands-reference.md) | When you need to look up a specific command's flags. |
| 4 | [troubleshooting.md](troubleshooting.md) | When something goes wrong. |
| 5 | [architecture.md](architecture.md) | When you need to understand why the system is built this way. Read once, reference later. |

## The two-layer architecture

Matchbox operates on top of Atma. See `atma/atma.md` and `matchbox/plans/marathon-plan-2026-04-21.md` for strategic context.

```
atma/              IDENTITY layer (who you are)
  shared/          rubric, CV template, cover letter template, fonts
  people/{name}/   your wiki (profile, CV, skills, stories, voice, log)

matchbox/          PIPELINE layer (what jobs exist, what you do)
  plans/           strategic plans (one-time reference)
  docs/            these guides
  shared/          db.py (SQLite access layer)
  workflows/       scan, score, tailor, apply, interview-prep briefs
  ui/              Streamlit review UI
  people/{name}/   your pipeline (DB, queue, output, reports, runs)
```

**Golden rule: Matchbox reads Atma. Matchbox writes only to Matchbox, except via ingest protocol when logging an application event.**

## The five slash commands

Invoked in Claude Code (not your terminal):

- `/scan-jobs` — daily scan, one mode or all, one country or all
- `/marathon` — big sweep, 4 modes x 5 countries, 200+ scored jobs
- `/tailor` — produce CV (+ optional cover letter) for one job or a batch
- `/apply` — log an application submission, update state, write to Atma log
- `/onboard-profile` — add a new person to the system

Detailed flags and examples in [commands-reference.md](commands-reference.md).

## The Streamlit UI

Launch:
```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 -m streamlit run matchbox/ui/ui.py --server.port 8501
```

Browse at http://localhost:8501. Ctrl+C to stop.

The UI is read + state-update only. It does not invoke Claude. When you queue a job, the UI writes to a YAML file; you then run `/tailor --batch` in Claude Code to process the queue.

## Budget envelope

Per `matchbox/profiles.yml`:

- Daily scans: ~$0.30-0.80 per run
- Marathons: ~$30-60 per sweep (soft cap $75)
- Tailor batch: $20 per 20 jobs
- Monthly cap: $300

You spend most of your budget on scoring (Sonnet reasoning over JDs) and tailoring (Sonnet with voice + factual audit passes). Discovery and filtering are cheap (Haiku).

## If this is your first time here

Go to [setup.md](setup.md).
