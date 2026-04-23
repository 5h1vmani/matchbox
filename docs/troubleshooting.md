# Troubleshooting

Common issues and fixes, in rough order of frequency.

## Streamlit

### "streamlit: command not found"

Two options:

```bash
# Option 1: always prefix with python3 -m
python3 -m streamlit run matchbox/ui/ui.py

# Option 2: add user pip bin to PATH (once)
echo 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Streamlit asks for email

`.streamlit/config.toml` exists but may not be read. Verify:

```bash
cat /Users/yantram/Desktop/Pinaka_speckit/.streamlit/config.toml
```

Must contain `gatherUsageStats = false`. Must be at repo root. Ensure you `cd` to repo root before running streamlit.

### Port 8501 already in use

```bash
lsof -ti:8501 | xargs kill -9
```

Or use a different port:

```bash
python3 -m streamlit run matchbox/ui/ui.py --server.port 8502
```

### UI shows "No jobs match" when you expect some

Check your filters. Most likely:
- "Hide cooling companies" is on and Anthropic is hidden
- Score range excludes the band your jobs are in
- State filter excludes `evaluated`

Uncheck "Hide cooling" and widen score range to 0.0-5.0 to see everything.

### UI renders but feels frozen or slow

Close the tab, reload. Streamlit's st.rerun() can leave stale state if a button handler errors. If persistent:

```bash
# Kill streamlit
lsof -ti:8501 | xargs kill -9

# Restart
cd /Users/yantram/Desktop/Pinaka_speckit
python3 -m streamlit run matchbox/ui/ui.py --server.port 8501
```

### ImportError: cannot import name 'db' from 'matchbox.shared'

You ran streamlit from the wrong directory. Always start from repo root:

```bash
cd /Users/yantram/Desktop/Pinaka_speckit   # MUST be here first
python3 -m streamlit run matchbox/ui/ui.py
```

## SQLite / DB

### `sqlite3.OperationalError: database is locked`

Another process is writing. Close the UI. Wait 10 seconds. Retry.

If persistent, WAL files may be stuck:
```bash
cd matchbox/people/shiva/db
ls -la
rm matchbox.db-wal matchbox.db-shm
```

### DB file does not exist

Run the smoke test to initialise:

```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 matchbox/shared/db.py shiva
```

### I need to inspect the DB directly

Use the `sqlite3` CLI:

```bash
sqlite3 matchbox/people/shiva/db/matchbox.db

sqlite> .tables
sqlite> .schema jobs
sqlite> SELECT id, company, role, total_score, state FROM jobs ORDER BY total_score DESC LIMIT 20;
sqlite> .quit
```

Or use the Python wrapper:

```python
import sys; sys.path.insert(0, '/Users/yantram/Desktop/Pinaka_speckit')
from matchbox.shared import db
print(db.get_stats('shiva'))
print(db.list_jobs('shiva', min_score=4.0, limit=10))
```

### I want to reset the DB completely

```bash
rm matchbox/people/shiva/db/matchbox.db
# Next agent invocation will re-init the schema
```

You will lose all scored jobs. Only do this in recovery scenarios.

## Scanning / marathon

### Marathon returned < 20 jobs when you expected 100+

Possible causes:
1. Cross-run dedup removed them all (already in DB from prior run)
2. Queries are stale — companies migrated ATSes or changed URLs
3. Geo filter is too aggressive

Check `runs/{date}-marathon/pipeline-log.md` for phase counts. Numbers like "raw_candidates: 200, survivors: 12" suggest aggressive filtering.

### Scanner hangs on one company's API

Check with a HEAD request:

```bash
curl -I https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
```

If 404, the slug is wrong — update `matchbox/people/shiva/search-queries-jobs.yml`. If 5xx or timeout, the service is down; rerun later or skip that company.

### Scan reports "budget exceeded" partway through

Either:
- Raise the budget cap in `matchbox/profiles.yml`
- Use `--budget-override 100.00` for one run
- Run narrower: `--modes dream --countries india,uk` instead of all

### I see the same company in multiple scans even though it should dedup

Check that it has the same URL. Dedup is by URL, not by (company, role). Company opens a role at a different URL → new row in DB. This is intentional — lets you see multiple postings at the same co.

## Tailor

### Tailor gate fails: "Rendering test - CV has 3 pages"

Master CV content grew. Two fixes:
1. Trim cv.md: reduce one project or compress a work experience section
2. Adjust cv-template.html: decrease font size or tighten margins

### Tailor gate fails: "Voice lint - em dashes found"

Agent introduced an em dash. Re-run `/tailor --id N` — it usually passes on retry because voice lint is in the workflow.

If persistent, the master cv.md contains an em dash. Run:

```bash
grep -n "—" atma/people/shiva/wiki/cv.md
```

Fix any found.

### Tailor gate fails: "Factual audit - private repo public claim"

Someone wrote "Pinaka is live at link in README" or similar. Pinaka is a private repo. Fix:
1. Edit the output HTML directly (if minor)
2. Or re-tailor: /tailor --id N

Update the factual audit workflow patterns if the phrasing is new (`matchbox/workflows/factual-audit.md`).

### Tailored CV has the wrong opening line

Re-tailor that specific job:

```
/tailor --id 135 --profile shiva --with-cover
```

Tell Claude specifically what to change if the default tailor keeps producing the same output. You can ask mid-tailor: "the opening should emphasize X not Y".

### PDF file is 0 bytes or missing

Chrome headless failed. Check Chrome is installed:

```bash
ls "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

If missing, install Chrome or update the CHROME path in the tailor workflow.

## Apply / state transitions

### /apply errors with "Job not in state 'tailored'"

The UI might have already transitioned state. Check:

```python
import sys; sys.path.insert(0, '/Users/yantram/Desktop/Pinaka_speckit')
from matchbox.shared import db
print(db.get_job('shiva', 135))
```

If state is `applied` already, no action needed. If `queued_for_tailor`, run `/tailor --id 135` first.

### /apply does not write to Atma log.md

Check file permissions:

```bash
ls -la atma/people/shiva/wiki/log.md
```

Must be writable by your user. If locked by another process, close and retry.

### UI state dropdown doesn't save my change

The dropdown requires clicking "Save state" (button beside it). Just changing the dropdown value does nothing until you click save.

## Budget / cost

### "Over monthly cap" error on scan

Check actual spend:

```python
import sys; sys.path.insert(0, '/Users/yantram/Desktop/Pinaka_speckit')
from matchbox.shared import db
print(db.get_stats('shiva')['total_cost_usd'])
```

If close to cap, raise it in `matchbox/profiles.yml`:

```yaml
total_monthly_max_usd: 500.00  # was 300.00
```

### I want to see what each scan cost

```python
import sys; sys.path.insert(0, '/Users/yantram/Desktop/Pinaka_speckit')
from matchbox.shared import db
for run in db.get_scan_history('shiva', limit=20):
    print(f"{run['id']:3d} | {run['mode']:20s} | {run['country']:15s} | ${run['cost_usd']:.2f} | {run['scored_count']:3d} jobs | {run['status']}")
```

## Fonts

### PDFs come out in system fonts, not Atkinson

Means the tailor did not use `cv-template.html` + base64 fonts. Look at the output HTML:

```bash
grep -c "@font-face" matchbox/people/shiva/output/jobs/2026-04-21/html/cv-*.html
```

Should be ≥ 2 (regular + bold). If 0, the tailor regressed to generating HTML inline. Re-run /tailor; check tailor.md workflow is enforcing template usage.

### I want to switch to IBM Plex Sans or Manrope

Edit `atma/people/shiva/wiki/profile.yml`:

```yaml
preferences:
  font: ibm_plex_sans   # was atkinson_hyperlegible
```

Next tailor run uses the new font. Verify font files exist:

```bash
ls atma/shared/fonts/
```

Should show files matching `font-config.yml` for the chosen font.

## Scheduling

### Claude Code scheduled task not firing

Claude Code scheduled tasks depend on the Claude Code app being open. If closed, tasks don't fire. Use OS cron for reliability:

```bash
crontab -e

# Add:
0 8 * * * cd /Users/yantram/Desktop/Pinaka_speckit && echo '/scan-jobs --profile shiva --mode dream --country india' | claude
```

## Atma / identity

### Tailor produces CV with old information

Master cv.md is out of date. Edit it:

```bash
open atma/people/shiva/wiki/cv.md
```

Next tailor picks up the changes. Do not edit tailored outputs directly for persistent changes.

### Atma log.md not updating after /apply

Verify the file:

```bash
cat atma/people/shiva/wiki/log.md | tail -20
```

Should show your recent applications. If nothing updated, the ingest protocol may be silently failing. Try running /apply again with `--dry-run` to see what it would do.

## General debugging

### Find out what a slash command actually did

Each command writes a pipeline log:

```bash
ls -la matchbox/people/shiva/runs/
cat matchbox/people/shiva/runs/2026-04-21-full-marathon/pipeline-log.md
```

Phase-by-phase, with timestamps.

### Verify configs are consistent

```bash
# Check profile.yml scoring weights sum to 1.0
python3 -c "
import yaml
data = yaml.safe_load(open('atma/people/shiva/wiki/profile.yml'))
scoring = data['scoring']
print(f'Sum: {sum(v for k,v in scoring.items() if k.endswith(\"_weight\"))}')
"
# Should print Sum: 1.0

# Check profiles.yml is parseable
python3 -c "
import yaml
data = yaml.safe_load(open('matchbox/profiles.yml'))
print(list(data['profiles'].keys()))
"
# Should print ['shiva'] (plus any new profiles)
```

### Nothing works and I need to reset

Staged recovery:

1. **Reset UI:** kill streamlit, restart fresh.
2. **Reset queue:** `rm matchbox/people/shiva/queue/tailor-queue.yml`
3. **Reset specific jobs:** UI → change state back to `evaluated`
4. **Reset DB (last resort):** `rm matchbox/people/shiva/db/matchbox.db` then re-run smoke test. Loses all pipeline state.

Do not nuke atma/ unless you know what you are doing. That is your identity data, not pipeline state.
