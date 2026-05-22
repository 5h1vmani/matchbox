# CLI reference

The CLI lives in `src/matchbox/cli.py` and is exposed as the `matchbox` script after `pip install`. Every command supports `--help`.

```bash
matchbox --help
matchbox <command> --help
```

## Commands

### `scan`

Probe ATS boards, score discovered jobs, insert new ones into the profile's DB.

```bash
matchbox scan PROFILE [--country uk|india|us] [--trial] [--dry-run] [--verbose]
```

| Flag | Default | Effect |
|---|---|---|
| `--country, -c` | (all) | Filter to one country |
| `--trial` | off | Mark this scan run as a trial in `scan_runs` |
| `--dry-run` | off | Probe + score, skip DB writes (preview only) |
| `--verbose, -v` | off | DEBUG-level logs |

If any jobs were inserted, prints a "Next: matchbox web" hint.

### `tailor`

Generate a tailored CV + cover letter for a single job.

```bash
matchbox tailor PROFILE JOB_ID [--model claude-sonnet-4-6] [--gate-mode warn|raise|skip]
```

| Flag | Default | Effect |
|---|---|---|
| `--model, -m` | `claude-sonnet-4-6` | Anthropic model name |
| `--gate-mode` | `warn` | `warn` logs, `raise` aborts on gate failure, `skip` returns None |

Costs depend on the routed tier (`bespoke` ~$10–20, `template` ~$0.05–0.30, `canonical` $0).

### `apply`

Mark a job as applied and stamp today's date.

```bash
matchbox apply PROFILE JOB_ID [--note "applied via LinkedIn referral"]
```

### `score-job`

Re-run the rubric on a single job and print the dimension breakdown. Persists the new scores.

```bash
matchbox score-job PROFILE JOB_ID
```

### `log-response`

Record an interview / rejection / offer / ghosted / other.

```bash
matchbox log-response PROFILE JOB_ID TYPE [--date 2026-05-01] [--note "screen call ok"]
```

`TYPE` is one of: `interview`, `rejection`, `offer`, `ghosted`, `other`.

### `analytics`

Print the conversion funnel + tier cost summary.

```bash
matchbox analytics PROFILE
```

Same data is available under the **Insights** page in the web dashboard.

### `rebuild-canonicals`

Regenerate all 3 geo variants of the canonical CV (`uk`, `india`, `relocate`) from the current profile. Run this after non-trivial profile edits.

```bash
matchbox rebuild-canonicals PROFILE
```

### `init-profile`

Create a new person directory with starter `profile.yaml`, `voice.yaml`, `stories.md`, `log.md`.

```bash
matchbox init-profile NAME
```

`NAME` should be lowercase, no spaces (validated against the same regex the web layer uses for profile slugs).

### `seed-demo`

Populate `people/demo/db.sqlite` with deterministic synthetic jobs. Idempotent unless `--force`.

```bash
matchbox seed-demo [--count 30] [--force]
```

### `web`

Start the FastAPI + HTMX dashboard.

```bash
matchbox web [--host 127.0.0.1] [--port 8765] [--reload]
```

| Flag | Default | Effect |
|---|---|---|
| `--host, -h` | `127.0.0.1` | Bind address. Anything other than loopback prints a red warning. |
| `--port, -p` | `8765` | Port |
| `--reload` | off | Auto-reload on code changes (dev) |

**Security:** see [SECURITY.md](../SECURITY.md). The dashboard has no auth; do not expose beyond loopback without a reverse proxy.

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for `tailor` (any tier that calls the LLM) |
| `MATCHBOX_PROFILE` | — | Default profile when visiting `/` in the web (else first alphabetically) |
| `MATCHBOX_COST_CONFIRM_USD` | `1.0` | Tailor actions whose high-estimate cost is at or above this require explicit confirmation |
| `MATCHBOX_DEBUG` | `0` | Enables `/api/docs` (FastAPI auto-docs) when set to `1` |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure (job not found, profile missing, etc.) |
| `2` | Typer-level CLI parse error (unknown flag, missing arg) |

## Configuration files

These are read by the CLI; document them here as a one-stop reference.

| Path | Purpose |
|---|---|
| `people/{name}/profile.yaml` | Candidate facts, target roles, scoring weights, exclusions |
| `people/{name}/voice.yaml` | Per-profile voice rules (banned words, openers, etc.) |
| `people/{name}/stories.md` | STAR+R career stories — used by tailor prompts |
| `people/{name}/anchor-packs.yaml` | Pre-approved bullets per role family |
| `people/{name}/db.sqlite` | All jobs, responses, scan history (gitignored) |
| `people/{name}/output/{job_id}/` | Generated CV + cover PDFs (gitignored) |
| `shared/rubric.yaml` | Universal scoring weight defaults |
| `shared/voice-rules.yaml` | Universal voice rule defaults |
| `shared/templates/*.typ` | Typst CV + cover-letter templates |
