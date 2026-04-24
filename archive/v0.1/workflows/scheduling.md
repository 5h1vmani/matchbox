---
id: scheduling
purpose: How to schedule Matchbox routines via Claude Code, OS cron, or on-demand. Scheduler-agnostic routines; this file explains each option and trade-offs.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-20
review_by: 2026-10-20
size_budget: 2000_tokens
---

# Scheduling Matchbox Routines

The slash commands (`/scan-jobs`, `/scan-programs`, `/apply`, `/onboard-profile`) are scheduler-agnostic. You can invoke them manually, via Claude Code scheduled tasks, or via OS-level cron. This file explains each option.

## Option A: Manual (on-demand)

Just type the command in Claude Code. Best when:
- Testing changes
- Running out-of-cadence for a specific event (new dream company announced a role, etc.)
- Running for a different profile than default

Examples:
```
/scan-jobs
/scan-jobs --profile shiva
/scan-jobs --profile brother --dry-run
/scan-programs --profile shiva --date 2026-04-28
```

No setup required. Always available.

## Option B: Claude Code Scheduled Tasks

If your Claude Code has the scheduled-tasks feature enabled (built-in or via MCP), you can register routines to fire on a cron schedule.

### Setup

Register schedules that match `matchbox/profiles.yml:profiles.{name}.schedule`. For Shiva (default profile):

- Daily jobs scan: `0 8 * * *` (8am IST every day)
- Weekly programs scan: `0 8 * * 1` (8am IST every Monday)
- Monthly Atma lint: `0 9 1 * *` (9am IST on the 1st)

### Invocation pattern

Each scheduled task should:

1. Open a Claude Code session (or use the sandbox/hooks pattern)
2. Run the appropriate slash command with `--profile <name>`
3. Wait for completion
4. On error, leave a note for the human (do not retry silently - schedulers should fail loud)

### Pros

- Integrated with Claude Code
- Task output and state tracked in the same tool where you review the digest
- Can chain tasks (run /scan-jobs, then /update-status on its output)

### Cons

- Tied to Claude Code being running/available
- Scheduler behavior depends on the specific Claude Code version
- If Claude Code is closed when the scheduled time arrives, the task may be delayed or skipped depending on configuration

## Option C: OS-level cron (macOS launchd / Linux cron / Windows Task Scheduler)

For maximum reliability, use the OS scheduler to invoke the `claude` CLI with a prepared prompt.

### macOS launchd example

Create `~/Library/LaunchAgents/com.shiva.matchbox.daily-jobs.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.shiva.matchbox.daily-jobs</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /Users/yantram/Desktop/Pinaka_speckit && echo '/scan-jobs --profile shiva' | claude 2>&1 | tee -a ~/matchbox-cron.log</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

Load with `launchctl load ~/Library/LaunchAgents/com.shiva.matchbox.daily-jobs.plist`.

### Linux cron example

Add to `crontab -e`:

```
# Daily jobs scan at 8am IST
0 8 * * * cd /path/to/Pinaka_speckit && echo '/scan-jobs --profile shiva' | claude 2>&1 >> ~/matchbox-cron.log

# Weekly programs scan at 8am IST Mondays
0 8 * * 1 cd /path/to/Pinaka_speckit && echo '/scan-programs --profile shiva' | claude 2>&1 >> ~/matchbox-cron.log
```

### Pros

- Independent of Claude Code being open
- Survives Claude Code updates
- OS-level logging (standard cron log locations)
- Works on servers (if you deploy this elsewhere later)

### Cons

- More setup per OS
- Requires the `claude` CLI to be installed and authenticated
- Error handling is more basic (you read the log; no rich digest UI)

## Option D: Hybrid (recommended for v1)

Use manual invocation for the first 2-3 weeks while tuning thresholds, then switch to OS-level cron once the pipeline behavior is stable and predictable.

Reasoning: automated scheduling amplifies both good and bad. Before automating, validate that:

- Your search-queries files surface useful candidates
- Thresholds are calibrated (not too loose, not too tight)
- Budget caps are realistic
- Digest output is actually actionable
- Quality gates catch real violations

Once those stabilize, automation adds leverage. Until then, it adds noise.

## Schedule Declarations in profiles.yml

`matchbox/profiles.yml:profiles.{name}.schedule` documents the INTENDED schedule per profile. It does NOT activate the schedule - it is a declarative statement that the scheduler (whichever you choose) is expected to honor.

Example from shiva's profile:
```yaml
schedule:
  daily_jobs: "0 8 * * *"
  weekly_programs: "0 8 * * 1"
  monthly_atma_lint: "0 9 1 * *"
```

This tells the OS cron entry (or Claude Code scheduled task) what to register. If you change the schedule here, update the scheduler registration too. The profiles.yml is documentation; the scheduler is execution.

## Budget Enforcement Under Automation

When routines are automated, budget overruns can accumulate silently. Protect with:

1. **Per-run hard cap** from `profile.budget.{routine}_max_usd`. Dispatcher stops the run if next phase would exceed.
2. **Monthly cap** from `profile.budget.total_monthly_max_usd`. Dispatcher refuses to start a run if monthly cap is already hit.
3. **Alerts.** Every digest includes cost. If a digest shows "DANGER: monthly cap 80% consumed," you see it next time you read the digest.

## Testing Schedules

Before trusting an automated schedule, test it:

1. Run the command manually once: `/scan-jobs --profile shiva`. Confirm digest is useful.
2. Run with `--dry-run` daily for 3 days: `/scan-jobs --profile shiva --dry-run`. Confirm no state pollution, digests still useful.
3. Register the schedule.
4. Check the digest daily for the first week. Look for: missed runs, quality-gate failures, budget overruns, empty digests.
5. If the first week looks right, trust the schedule.

## Operational Notes

- **Runs collision:** if two runs of the same routine fire in the same day (e.g., manual + scheduled), the second should detect the first run's folder exists and prompt for overwrite. Dispatcher handles this.
- **Timezone handling:** all cron expressions in profiles.yml assume IST (UTC+5:30). If you run from a different timezone, adjust.
- **Failure notification:** v1 relies on you reading the digest daily. v2 can add email/Slack notifications on critical failures. Not built yet.
- **Resuming a failed run:** if a run crashed mid-phase, `/scan-jobs --profile shiva --phase 4` picks up at phase 4 using existing intermediate state.
