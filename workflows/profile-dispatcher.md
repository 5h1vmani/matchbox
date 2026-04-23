---
id: profile-dispatcher
purpose: Shared logic for --profile argument parsing, validation, and path substitution. Called by every Matchbox task entry point before running the task body.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-21
review_by: 2026-10-21
size_budget: 2000_tokens
---

# Profile Dispatcher

Every Matchbox task begins by resolving the profile: which person is this run for? This workflow standardizes that resolution.

## Invocation

Called at the top of every Matchbox task. Entry points include:
- Claude Code slash commands in `.claude/commands/*.md` (convenience layer)
- Direct workflow invocation (paste `matchbox/workflows/*.md` into any Sonnet session)
- The Master Operator Prompt at `matchbox/MASTER.md`

This file is not itself an entry point — it is a shared step.

## Inputs

- The task arguments as a string (from whichever entry point invoked the task)
- `matchbox/profiles.yml` - the profile registry

## Outputs

Either:
- Resolved profile object (full_name, paths, mode, budget, tracks_enabled, etc.)
- Clean failure with user-readable message

## Algorithm

### Step 1: Parse arguments

Look for these arguments in the task arguments string (whitespace-separated):

| Flag | Shape | Default |
|------|-------|---------|
| `--profile <name>` | string | read `default:` from profiles.yml |
| `--date <YYYY-MM-DD>` | date string | today's date (system date) |
| `--dry-run` | boolean flag | false |
| `--phase <N>` | integer | all phases run |
| `--budget-override <usd>` | float | no override |

Unknown flags: warn, do not fail. Continue.

### Step 2: Load profiles.yml

Read `matchbox/profiles.yml`. Verify file exists and parses. If not, fail with:

```
Cannot read matchbox/profiles.yml. Pipeline halted.
```

### Step 3: Resolve profile

- If `--profile` not provided: use `profiles.yml:default`.
- Look up `profiles:{name}` in profiles.yml.
- If not found, fail with:

```
Profile '{name}' not found in matchbox/profiles.yml.
Available: {list all profiles with enabled=true}.
```

- If found but `enabled: false`, fail with:

```
Profile '{name}' is disabled. Edit matchbox/profiles.yml to enable, or run /onboard-profile to initialize.
```

### Step 4: Validate required files exist

For the resolved profile, check every file in `profiles.yml:validation.required_files_per_profile`:

- `{profile.paths.atma}/profile.yml`
- `{profile.paths.atma}/cv.md`
- `{profile.paths.atma}/narrative.md`
- `{profile.paths.atma}/voice.md`
- `{profile.paths.matchbox}/mode.yml`
- `{profile.paths.matchbox}/applications.md`

Plus track-specific files based on `tracks_enabled`:
- If `tracks_enabled.jobs: true`: `{matchbox}/search-queries-jobs.yml`
- If `tracks_enabled.programs: true`: `{matchbox}/search-queries-programs.yml`

Any missing file → fail with list of missing paths. Do not proceed.

### Step 5: Check track enablement

If the invoking task is `scan-jobs` (or `marathon`, `tailor`, `apply`), confirm `profile.tracks_enabled.jobs == true`.
If the task is `scan-programs`, confirm `profile.tracks_enabled.programs == true`.

If the required track is not enabled for this profile:

```
Profile '{name}' does not have track '{track}' enabled. 
Edit matchbox/profiles.yml to enable, or use a different profile.
```

### Step 6: Check budget

Read the profile's budget caps. For the current month, sum the costs logged in all `runs/` pipeline-log.md files. If current monthly spend + expected-run-cost exceeds `total_monthly_max_usd`, fail with:

```
Profile '{name}' monthly budget ({total_monthly_max_usd}) would be exceeded.
Current spend: ${current_monthly_spend}. Override with --budget-override or wait for next month.
```

### Step 7: Return resolved context

Return an object containing:

```yaml
profile_name: <name>
full_name: <full_name>
mode: <mode>
paths:
  atma: <path>
  matchbox: <path>
tracks_enabled:
  jobs: <bool>
  programs: <bool>
budget:
  per_run_cap: <usd>
  remaining_monthly: <usd>
notification:
  surfaced_score_min: <float>
  max_daily_surface: <int>
args:
  date: <date>
  dry_run: <bool>
  phase: <int or null>
run_folder: matchbox/people/{name}/runs/{date}-{routine}/
```

The invoking command uses this context to run the orchestration brief with correctly substituted paths.

## Error Format

All failures return a structured error:

```
DISPATCHER ERROR
Routine: /{command_name}
Profile arg: {raw arg}
Failure: {what went wrong}
Suggested fix: {specific action}
```

This is the message shown to the user. Do not add flowery language or apologies. Fail cleanly with specific remediation.

## Dry Run Behavior

If `--dry-run` is set:

- All phases execute
- All files are written to `runs/{date}-{routine}/` as normal (intermediate state)
- Production artefacts (output/ and reports/ and applications.md updates) are NOT written
- Digest.md is still generated but prefixed: "DRY RUN - no production artefacts written"

This enables testing the pipeline without polluting the pipeline state.

## Phase Override

If `--phase <N>` is set:

- Skip all phases before N
- Require intermediate state files from previous phases to exist in `runs/{date}-{routine}/`
- If earlier phase files are missing, fail with: "Cannot start at phase N; missing phase M output. Run without --phase to start fresh."
- Execute only phase N and then stop (do not continue to N+1)

Used for debugging a specific phase.

## Budget Override

If `--budget-override <usd>` is set, replace `total_monthly_max_usd` with the provided value for this invocation only. Does not persist.

Used for emergency runs when the normal budget would block.

## Logging

Every dispatcher invocation writes to `matchbox/people/{name}/runs/{date}-{routine}/pipeline-log.md`:

```
[HH:MM:SS] Dispatcher called for command /{command}
[HH:MM:SS] Resolved profile: {name} (mode: {mode})
[HH:MM:SS] Validated required files: PASS
[HH:MM:SS] Track check ({track}): PASS
[HH:MM:SS] Budget check: PASS ($X spent this month of $Y cap)
[HH:MM:SS] Dispatcher returning context to orchestration brief
```

This log is the first debugging resource if a routine fails mid-phase.

## Rationale

Why a separate dispatcher instead of inlining this logic in each command?

1. **DRY.** Every command needs the same resolution logic. One file owns it.
2. **Testability.** Dispatcher can be smoke-tested independently.
3. **Single place to update.** When we add new validation rules (e.g., signed profile state, remote config), one file changes.
4. **Clean command files.** Each `.claude/commands/*.md` stays focused on the specific routine.

## The Read/Write Contract (strict enforcement)

The dispatcher enforces a one-way contract between Matchbox and Atma. This is the rule that makes the system trustworthy.

**Matchbox READS from Atma (allowed):**
- `atma/people/{name}/wiki/profile.yml` (for filters, keywords, scoring weights, dream_companies)
- `atma/people/{name}/wiki/skills.md`, `preferences.md`, `projects.md`, `log.md#last-30d` (per task routing)
- `atma/people/{name}/wiki/cv.md`, `narrative.md`, `voice.md`, `story-bank.md` (for cv_tailoring task)
- `atma/shared/scoring-rubric.md`, `cv-template.html`, `cover-letter-template.html`, `ai-detection-guide.md`, `ingest-protocol.md`, `fonts/*` (all shared infrastructure)

**Matchbox WRITES to Matchbox (allowed):**
- `matchbox/people/{name}/runs/{date}-{routine}/*` (per-run state files, logs, digests)
- `matchbox/people/{name}/reports/*` (evaluation reports)
- `matchbox/people/{name}/output/*` (tailored CVs and cover letters)
- `matchbox/people/{name}/applications.md` (pipeline state updates)
- `matchbox/people/{name}/well-funded-watchlist.yml` (funding watchlist, with TTL)

**Matchbox WRITES to Atma (narrowly allowed, ONE path only):**
- Only the `/apply` command writes to `atma/people/{name}/wiki/log.md`, via the ingest protocol's 5-question ritual. Every other Matchbox operation is read-only on Atma.

**Matchbox must NOT:**
- Write to `atma/people/{name}/wiki/profile.yml`, `cv.md`, `narrative.md`, or any wiki file other than log.md
- Write to `atma/shared/*` (that is global configuration; only Opus-led lint cycles may propose changes there)
- Read `atma/people/{name}/wiki/comp.md`, `network.md`, or `traction.md` unless the task routing explicitly permits (comp.md is NEVER readable under any task for security)

The dispatcher verifies this contract at startup by attempting no writes to Atma except via ingest protocol. Any proposed Atma write not routed through ingest fails the run with a contract violation error.

## Rationale for the read-only Atma rule

Identity drifts slowly. Pipeline state drifts daily. Mixing them corrupts identity.

- If daily scans could edit `profile.yml`, an agent could silently adjust your scoring weights or add a keyword, and you would not know until your rubric stopped matching your preferences.
- If scoring could edit `skills.md`, an agent could infer a skill from a JD match and add it to the wiki, inflating your claims.
- If tailoring could edit `cv.md`, every tailored CV would permanently contaminate the master.

The one-way contract is a safety rail. `/apply` is the only write-back path, and it runs through the ingest protocol's 5-question ritual. You cannot silently pollute the identity layer through automation.
