# Operator runbook

Day-to-day commands for running the pipeline.

## Daily scan

```bash
# Probe all known ATS boards, score, insert new jobs
matchbox scan shiva

# UK only
matchbox scan shiva --country uk

# Dry run — probe + score, skip DB writes
matchbox scan shiva --dry-run --verbose
```

## Review new jobs

```bash
# Open dashboard
matchbox web

# CLI: list top-scored evaluated jobs
sqlite3 people/shiva/db.sqlite \
  "SELECT id, company, role, total_score, tier FROM jobs \
   WHERE profile_name='shiva' AND state='evaluated' \
   ORDER BY total_score DESC LIMIT 20"
```

## Tailor a job

```bash
# Check score first
matchbox score-job shiva 42

# Tailor (bespoke/template: calls API; canonical: copies pre-rendered PDF)
matchbox tailor shiva 42

# Tailor with gate mode raise (fail on violations)
matchbox tailor shiva 42 --gate-mode raise
```

## Apply

```bash
matchbox apply shiva 42
matchbox apply shiva 42 --note "Applied via LinkedIn"
```

## Log outcomes

```bash
# Invite received
matchbox log-response shiva 42 interview

# Rejection
matchbox log-response shiva 42 rejection --note "No fit on seniority"

# Offer
matchbox log-response shiva 42 offer --date 2026-05-01

# Ghosted after response
matchbox log-response shiva 42 ghosted
```

## Follow-up check

```bash
matchbox analytics shiva
# Shows conversion funnel and flags jobs that need a nudge
```

Or in the dashboard: **Follow-ups** tab.

## Rebuild canonical PDFs

Run this when `profile.yaml` changes significantly or after editing `shared/templates/*.typ`.

```bash
matchbox rebuild-canonicals shiva
# Outputs: people/shiva/output/canonical-{uk,india,relocate}.pdf
#           people/shiva/output/canonical-cover-{uk,india,relocate}.pdf
```

## Add a new ATS source

1. Find the company's ATS slug (the URL subdomain on their jobs board).
2. Add to `src/matchbox/discovery/sources.py → KNOWN_SOURCES`:
   ```python
   greenhouse("new-company", "New Company", country="uk", sector="ai"),
   ```
3. Next `matchbox scan` picks it up automatically.

## Probe a funded company

```python
from matchbox.discovery.scan_funding import probe_funded_companies

results = probe_funded_companies([
    {"name": "Embra", "ats": "ashby", "slug": "embra", "country": "us", "sector": "ai"},
], profile="shiva")
```

## Troubleshooting

### `typst not found`
Install: `brew install typst` or `cargo install typst-cli`.
Canonical-tier tailing does not need Typst (pre-rendered copy only).

### `anthropic.AuthenticationError`
Check `ANTHROPIC_API_KEY` is set. Only `matchbox tailor` (non-canonical) calls the API.

### DB locked / WAL error
SQLite WAL mode is enabled; multiple readers are safe.
If stuck: `sqlite3 people/shiva/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE)"`.

### ATS probe returns 0 jobs
- Check `source.base_url` is still valid (ATS slugs occasionally change).
- Run `--verbose` to see per-source counts.
- Test manually: `curl -s "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs" | python -m json.tool | head -50`.

### Gate violations on generated content
Use `--gate-mode warn` (default) to continue, `--gate-mode raise` to fail, or `--gate-mode skip` to abandon that job.
Check `shared/voice-rules.yaml` and `people/shiva/voice.yaml` for the rule that triggered.
