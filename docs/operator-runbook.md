# Operator Runbook

Day-to-day workflow for running Matchbox. Read this every time you sit down to work on job search.

## The session flow (mental model)

```
1. Scan       →  2. Review in UI   →  3. Queue         →  4. Tailor
(agent)          (you + browser)      (you, buttons)       (agent)
                                                               ↓
                                                           5. Review PDFs
                                                               ↓
                                                           6. Submit on portal
                                                               ↓
                                                           7. Log the submission
                                                               (you + /apply)
                                                               ↓
                                                           8. Track responses
                                                               (you + state)
```

Each step has a distinct trigger and owner. Do not skip or mix steps.

## 1. Scan (agent, in Claude Code)

Choose one of three scan cadences:

### Daily quick check (~$0.30-0.80)

```
/scan-jobs --profile shiva --mode dream --country india
/scan-jobs --profile shiva --mode dream --country uk
```

Cheap, high signal-to-noise. Good for morning check if you have active applications already pending.

### Targeted gap-fill or mode drill (~$1-5)

```
/scan-jobs --profile shiva --mode roles --country us
/scan-jobs --profile shiva --mode niches
```

Use when you want to expand coverage in a specific direction.

### Marathon (~$30-60)

```
/marathon --profile shiva
```

Once per week at most. Full 4 modes x 5+ countries. Produces 50-150 new scored jobs.

Subsequent marathons auto-dedup against DB, so you only see new jobs each time.

## 2. Review in UI (browser)

Launch:
```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 -m streamlit run matchbox/ui/ui.py --server.port 8501
```

Open http://localhost:8501. Default filters hide cooling companies (e.g., Anthropic if you have 3+ apps there) and show only APPLY-band jobs you have not yet queued.

### How to review efficiently

1. **Summary bar (top):** counts by state. Watch "Evaluated" (needs review) and "Applied" (awaiting response).
2. **Filters (sidebar):** narrow by country, score range, mode, recommendation. Useful for focus sessions (e.g., "just Canada jobs today").
3. **Job rows:** click to expand. Read:
   - Company + role
   - Score breakdown (CV match, north star, comp, cultural, red flags)
   - Location + comp + visa sponsorship
   - Full report (in "📄 Full report" expander)
4. **Use the notes:** the "Tailoring Notes" section in each report tells the tailor agent what to emphasize. Read it to know if the fit is real or surface-only.

### Decision per job

- **Strong fit (score ≥ 4.2, company you want, visa path works):** Queue for CV + cover (click "📝+✉")
- **Good fit (4.0-4.2):** Queue for CV only (click "📝"). Skip cover unless portal requires.
- **Maybe fit (3.5-3.9, REVIEW band):** Leave alone for now. Revisit at end of week if pipeline is thin.
- **Bad fit (<3.5):** Change state to "skip" via dropdown, or ignore.
- **Do not want:** Add company to "Exclude specific companies" multi-select. Persists for your session.

## 3. Queue (you, UI buttons)

Clicking "📝 CV" or "📝+✉" in the UI:
- Changes state to `queued_for_tailor`
- Appends to `matchbox/people/shiva/queue/tailor-queue.yml`

Verify:
```bash
cat matchbox/people/shiva/queue/tailor-queue.yml
```

Queue 15-25 jobs per session. Too few = wasteful batch cost; too many = quality control slips.

## 4. Tailor (agent, in Claude Code)

```
/tailor --batch --profile shiva
```

This processes up to 20 queued jobs:
- Reads queue
- For each job: pulls master CV + Atma files, runs the 10-step tailor workflow
- Runs three quality gates (rendering test, factual audit, voice lint)
- Writes output files
- Updates DB state `queued_for_tailor` → `tailored`
- Removes from queue

**Budget:** $20 per invocation. Takes 15-30 minutes depending on queue size.

If queue > 20, run `/tailor --batch` multiple times.

## 5. Review PDFs (you)

Output path:
```
matchbox/people/shiva/output/jobs/2026-04-21/pdfs/
├── cv-{company-slug}-{role-slug}.pdf
└── cover-{company-slug}-{role-slug}.pdf   (if --with-cover)
```

Open each PDF. Check:

- **Opening line** anchors on your strongest fact for this role (usually 250K CCU or Claude Code experience)
- **Keywords** from the JD appear but do not feel forced
- **Voice** matches yours: short sentences, no "spearheaded," no em dashes, specific numbers
- **Dates** match your actual history
- **Length**: CV is exactly 2 pages; cover letter is 1 page
- **No private-repo claims**: Pinaka and Kubera are private; text should not say "link in README"
- **No AI tells**: no uniform bullet structure, no rounded metrics everywhere

If anything is wrong, come back to Claude Code and say "re-tailor job 135 and fix the opening line — should mention X not Y" and I will fix specifically that one job.

## 6. Submit on portal (you + browser)

For each reviewed PDF:

1. Open the job URL (from UI or report)
2. Click Apply on the company's ATS (Greenhouse, Ashby, Lever, or the company's own portal)
3. Upload the CV PDF. Paste or upload the cover letter PDF.
4. Fill in the form (name, email, phone, work history Q&A, visa status, etc.)
5. Submit

No shortcuts. Each submission is human action.

## 7. Log the submission (in Claude Code)

Immediately after submitting:

```
/apply --id 135 --profile shiva --notes "Applied via Greenhouse. No referral."
```

Where 135 is the job ID shown in the UI.

This:
- Updates DB state `tailored` → `applied`
- Stamps `applied_date`
- Writes an entry to `atma/people/shiva/wiki/log.md` via the ingest protocol (your identity layer)
- Future scans use this date for cooling calculation

Alternatively: in the UI, click the "📤 Mark Submitted" button (updates DB only; you still need to run `/apply --id N` later to write to Atma log).

## 8. Track responses (as they come)

When a recruiter replies:

- **Screen call scheduled:** UI → change state to `responded` or `interview`. Add notes about who contacted you and when.
- **Rejection:** UI → change state to `rejected`. Add `rejection_reason` via state dropdown + note.
- **Offer:** UI → change state to `offer`. Celebrate. Then think about negotiation using your `atma/people/shiva/wiki/comp.md`.

When an interview is scheduled, run (future command):

```
/interview-prep --id 135 --profile shiva
```

Generates prep notes with 5 research queries, round-by-round breakdown, STAR+R story mapping.

## Weekly rhythm (suggested)

| Day | What |
|-----|------|
| Monday | Marathon scan in morning. Review + queue 15-20 in afternoon. Tailor batch evening. |
| Tuesday | Submit 10-15 applications. Log each one. |
| Wednesday | Submit remaining 5-10 from Monday's batch. Daily dream scan in AM. |
| Thursday | Targeted scan (niches or a specific country). Queue 5-8. Tailor. |
| Friday | Submit Thursday batch. Check response inbox. Update states for any replies. |
| Weekend | Rest. Or interview prep for any upcoming interviews. |

You submit ~20-30 applications per week at quality. Over 4 weeks, that is 80-120 submissions. At 20-30% screen conversion, expect 15-30 interviews. Matches the target.

## How to know if something is off

- **Scan surfaces < 30 new jobs in a marathon:** queries are stale or too narrow. Revisit `search-queries-jobs.yml`.
- **Scoring clusters 3.5-4.0 with nothing above 4.5:** rubric is too conservative, or your profile filters are too broad. Tune weights in `atma/people/shiva/wiki/profile.yml:scoring`.
- **Tailored CV has AI tells:** the voice rules didn't catch something. Tell the tailor specifically what to fix. Update `atma/shared/ai-detection-guide.md` if it's a repeated pattern.
- **UI shows "Hidden N jobs from excluded companies":** your filter is working. Uncheck "Hide cooling" to verify.
- **Recruiter responses low (<15% from 30+ applications):** CV framing isn't landing. Audit 5 tailored CVs against target JDs for keyword coverage and voice consistency.

## What not to do

- **Do not auto-apply.** Ever. Submission is always a human clicking a portal button. The tool prepares; you submit.
- **Do not tailor everything.** Queue 15-25 per session, not 80. Diligent review of 20 beats spraying 100.
- **Do not skip state logging.** If you submit without running /apply, the DB loses sync with reality and cooling filters break.
- **Do not edit cv.md mid-session.** Master CV changes affect all future tailorings. Update at end of session or between sessions.
- **Do not share the SQLite DB.** It contains your pipeline state including rejection reasons, notes, and is gitignored for a reason.

## End of session checklist

- All queued jobs tailored? (`queue/tailor-queue.yml` should be empty or nearly so)
- All tailored jobs reviewed? (Open PDFs, confirm voice)
- All submissions logged? (UI state column: no "tailored" rows for things you actually submitted)
- DB state saved? (SQLite auto-commits; no action needed, just verify no "lock" errors)
- Streamlit closed? Ctrl+C in terminal.
