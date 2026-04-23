---
id: daily-scan-jobs
purpose: Orchestration brief for Sonnet. Runs the daily jobs scan funnel. Invokes Haiku subagents per phase. Produces a digest.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-20
review_by: 2026-10-20
size_budget: 4000_tokens
---

# Daily Scan Jobs Orchestration Brief

You are the Sonnet orchestrator for Shiva's daily jobs scan routine. Read this brief, execute each phase (invoking Haiku subagents where indicated), aggregate results, run quality gates, write a digest for human review.

## Invocation

- **Automated:** Claude Code scheduled task at 08:00 IST daily, OR an OS cron job (see `matchbox/docs/troubleshooting.md#scheduling`)
- **Manual:** any of:
  - Claude Code: `/scan-jobs` or `/scan-jobs --date YYYY-MM-DD`
  - Any Sonnet session: paste this file and provide the date (or today)
  - CLI: not implemented yet; would invoke this workflow via a thin wrapper

## Inputs (read these first)

1. `matchbox/people/shiva/search-queries-jobs.yml` — role queries, dream companies, platform sweeps
2. `atma/people/shiva/wiki/profile.yml` — title filters, scoring weights, geography policy, deal-breakers, dream companies
3. `matchbox/people/shiva/applications.md` — existing pipeline (for dedup)
4. `matchbox/people/shiva/mode.yml` — current mode (passive/warm/active), thresholds, scan frequency
5. `atma/shared/scoring-rubric.md` — 5-dimension rubric
6. `matchbox/shared/states.yml` — canonical state machine

## Output Artefacts

Per run, write to `matchbox/people/shiva/runs/YYYY-MM-DD-daily-jobs/`:

```
runs/YYYY-MM-DD-daily-jobs/
├── phase-1-discover.json     raw results from all queries
├── phase-2-filter.json       survivors after dedup + geo + title filter
├── phase-3-fetch.md          full JDs for survivors
├── phase-4-score.md          per-JD reports with scores
├── phase-5-tailor.md         tailored CVs + covers for score >= tailor_min
├── pipeline-log.md           timestamps, costs, errors, decisions
└── digest.md                 user-facing summary
```

Production artefacts (tailored CVs + covers) go to `matchbox/people/shiva/output/jobs/`.
Scoring reports (per opportunity) go to `matchbox/people/shiva/reports/jobs/`.
Application rows appended to `matchbox/people/shiva/applications.md` with state `evaluated`.

## Budget

- Maximum 100K tokens per run
- Maximum $2 USD per run
- If exceeded, STOP at current phase, flag in pipeline-log.md, write partial digest

## Phase-by-Phase

### Phase 1: DISCOVER (Haiku)

**Delegate to Haiku subagent with this prompt:**

> Read `matchbox/people/shiva/search-queries-jobs.yml`. Execute every query in `role_queries`, every `site_search` under `dream_companies`, and every query under `platforms`. Prefer structured API calls where `greenhouse_api` or `ashby_api` URLs are present.
>
> ALSO read `matchbox/people/shiva/well-funded-watchlist.yml`. For every entry in `watchlist:` where `ttl_expires >= today`:
>   - If `careers_url` is set and `ats_platform` is known (ashby/lever/greenhouse), issue one structured query for that company's careers page using the `watchlist_ats_templates` from `search-queries-jobs.yml:funded_recent_queries`.
>   - If `ats_platform` is unknown, skip this entry for this run.
>   - Stamp each discovered role with `source_query: "watchlist:{company}"` and `dream_tier: tier_4_exploratory` so downstream phases can carry that signal.
>
> Return a JSON array of candidate roles, each with: `{title, company, location, url, snippet, source_query, dream_tier (if from watchlist)}`. No dedup here; that is Phase 2. Budget: 5K tokens.

**Write output to:** `runs/YYYY-MM-DD-daily-jobs/phase-1-discover.json`

**Expected count:** 30-80 raw hits + variable from watchlist (currently empty; grows over time via /scan-funding-news).

**Failure handling:**
- Primary API down (Greenhouse, Ashby): retry once, then fall back to LinkedIn site-search for that company
- >5 queries fail: STOP, log, notify user
- 0 results returned: verify network, re-run once; if still 0, STOP

### Phase 1b: WATCHLIST FRESHNESS (added 2026-04-21)

After discovery completes, run HEAD-checks on every active watchlist entry's careers URL:

```python
import yaml
from pathlib import Path
from matchbox.shared import db

wl_path = Path("matchbox/people/shiva/well-funded-watchlist.yml")
wl = yaml.safe_load(wl_path.open()) or {"watchlist": [], "archive": []}
today = datetime.date.today().isoformat()

for entry in list(wl.get("watchlist", [])):
    url = entry.get("careers_url")
    if not url:
        continue
    status = db._http_status(url)      # reuses the helper from db.py
    entry["url_last_checked"] = today
    entry["url_http_status"]  = status

    # Track consecutive failures
    failures = entry.get("url_failures", 0)
    if status in (404, 410, 0):
        entry["url_failures"] = failures + 1
    else:
        entry["url_failures"] = 0

    # Archival rule: 3 strikes on 4xx/0 → archive
    if entry["url_failures"] >= 3:
        entry["archived_reason"] = f"careers page {status} for 3+ consecutive checks"
        entry["archived_date"]   = today
        wl.setdefault("archive", []).append(entry)
        wl["watchlist"].remove(entry)

# Dormancy rule: no new roles in 90 days → archive
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(days=90)).date().isoformat()
for entry in list(wl.get("watchlist", [])):
    last_role = entry.get("last_role_discovered_date")
    if last_role and last_role < cutoff and entry.get("roles_seen", 0) == 0:
        entry["archived_reason"] = "dormant: no roles in 90d"
        entry["archived_date"]   = today
        wl.setdefault("archive", []).append(entry)
        wl["watchlist"].remove(entry)

yaml.safe_dump(wl, wl_path.open("w"), default_flow_style=False, sort_keys=False)
```

Expected duration: ~30s for 100 watchlist entries (HEAD requests at ~1s each, rate-limited).

### Phase 2: DEDUP + FILTER + GEO (Haiku)

**Delegate to Haiku:**

> Read `runs/YYYY-MM-DD-daily-jobs/phase-1-discover.json`. Read `matchbox/people/shiva/applications.md` to extract existing applications. Read `atma/people/shiva/wiki/profile.yml` for title filters and geography policy.
>
> For each candidate:
> 1. **Dedup:** normalize company + title + location. If already in applications.md, drop.
> 2. **Title filter:** must match at least one positive keyword from profile.yml `title_filters.positive`. Must not match any negative keyword. Mark seniority_boost matches.
> 3. **Geo filter:** apply `profile.yml:geography_policy`. Dream-company listed → any location passes. Non-dream → India-only or remote-from-India. Drop non-dream roles requiring relocation outside India.
> 4. **Deal-breakers:** drop any role matching `profile.yml:deal_breakers`.
>
> Return JSON: survivors list with fields `{title, company, location, url, snippet, source_query, seniority_boost: bool, is_dream_company: bool}`. Include a `dropped_count` by reason for reporting.

**Write to:** `phase-2-filter.json`

**Expected survivors:** 20-40% of Phase 1 count, typically 8-25.

**Failure handling:** Haiku decision errors → log and proceed. Too few survivors (<3) → reasonable, not failure. Too many (>50) → filters may be too loose; flag in pipeline-log.

### Phase 3: FETCH (Haiku)

**Delegate to Haiku:**

> Read `runs/YYYY-MM-DD-daily-jobs/phase-2-filter.json`. For each survivor, fetch the full JD. Prefer structured API responses. Fall back to web fetch with extraction.
>
> Extract ONLY:
> - Role overview / mission
> - Key responsibilities
> - Required qualifications
> - Preferred qualifications
> - Compensation if stated
> - Location / remote policy
> - Visa sponsorship statement if present
> - Posting age if detectable
>
> Skip: footers, ads, company boilerplate, legal notices, application instructions, perks lists.
>
> Return as a markdown file with one `## {Company} - {Role}` section per survivor, each containing the extracted JD body. Budget: ~500 tokens per JD.

**Write to:** `phase-3-fetch.md`

**Failure handling:**
- Site returns 403/blocked: try LinkedIn site-search fallback, then Glassdoor, then mark as "JD unavailable" and downweight in scoring
- Fetch returns empty: mark `legitimacy: caution - empty JD`, flag for manual review

### Phase 4: SCORE (Sonnet - you do this)

For each JD in `phase-3-fetch.md`:

1. **Legitimacy check first.** Apply `atma/shared/scoring-rubric.md` pre-scoring gate:
   - Posting age > 60 days → flag `ghost`, skip to Phase 5 without tailor
   - Apply button dead or JD empty → flag `caution`, proceed with reduced confidence

2. **Read routing-allowed Atma files ONCE for this entire phase:**
   - `atma/people/shiva/wiki/profile.yml` (full)
   - `atma/people/shiva/wiki/skills.md`
   - `atma/people/shiva/wiki/preferences.md`
   - `atma/people/shiva/wiki/projects.md`
   - `atma/people/shiva/wiki/log.md` last 30 days (if accessible via grep on dates)
   - (Do NOT read comp.md, network.md, traction.md, writing-samples/* - denied by routing for job_scoring)

3. **Score each JD:** 5 dimensions 1-5, cite specific JD text or profile fact. Apply weights from `profile.yml:scoring`. Sum to final score.

4. **Per-role report:** write to `matchbox/people/shiva/reports/jobs/{NNN}-{company-slug}-{YYYY-MM-DD}.md` using the template in `matchbox/workflows/score.md` Step 4.

5. **Apply Ashby LLM-summary rule:** in each report's "Tailoring Notes" section, explicitly list the 5-7 JD keywords that must appear in the tailored CV's first 500 words.

6. **Append to applications.md:** one row per scored opportunity with state `evaluated` (or `skip` if score < 3.5 OR ghost).

**Write aggregate to:** `phase-4-score.md` (summary of all scored roles, ranked)

**Budget:** ~8-10K tokens per JD scored.

### Phase 5: TAILOR (Sonnet, conditional)

Trigger: any role scoring ≥ `mode.yml:thresholds.tailor_min` (currently 3.5 in warm mode).

For each qualifying role, invoke the full `matchbox/workflows/tailor.md` process. Critical: do NOT skip Steps 9.5 (rendering test), 9.6 (factual audit), and 10 (voice lint). All three must pass before the tailored artefact is promoted to `output/jobs/`.

**Multi-application hygiene:** if applying to more than one role at the same company today, drop cross-reference paragraphs from all cover letters per `tailor.md` rules.

**Budget:** ~25-30K tokens per tailored pair (CV + cover letter).

**Write aggregate to:** `phase-5-tailor.md` (list of tailored pairs with paths)

### Phase 6: QUALITY GATES (Haiku, grep-based)

For every tailored CV and cover letter, run:

1. **Rendering test:** headless Chrome PDF generation. CV must be 2 pages. Cover letter must be 1 page. Fail if not.
2. **Factual audit:** per `matchbox/workflows/factual-audit.md`. Must pass all 7 checks.
3. **Voice lint:** `grep -c "—"` (em dashes) = 0. Contractions = 0. Banned phrases = 0.

**Any failure:** reject the tailored artefact. Keep the scoring report. Log in `pipeline-log.md`. Do NOT promote to `output/jobs/`.

**Log to:** `pipeline-log.md` with line items per gate result.

### Phase 7: DIGEST (Sonnet - you write this)

Write `runs/YYYY-MM-DD-daily-jobs/digest.md` with:

```
# Daily Scan Jobs - YYYY-MM-DD

## Summary
- Phase 1 Discover: N candidates from {N_queries} queries
- Phase 2 Filter: N survived ({reasons for drops})
- Phase 3 Fetch: N JDs fetched (M failed)
- Phase 4 Score: N scored (distribution breakdown)
- Phase 5 Tailor: N tailored (thresholds hit)
- Phase 6 Quality Gates: N passed, M failed (with reasons)

## Surfaced (score >= surface_min, typically 4.0)
{Per role: company, title, location, score, report link, tailored CV link}

## Tailored-and-waiting (score >= tailor_min, typically 3.5)
{Per role: company, title, location, score, tailored CV path}

## Skipped / Below Threshold
{Short list, not detailed}

## Blocked or Failed
{Anything that hit an error; what to investigate}

## Cost
Tokens consumed: N
Estimated cost: $X
Within budget: yes/no

## Next Action for User
- Review surfaced roles (N items)
- Decide which to submit
- For each submitted: say "submitted {company} {role}" to trigger apply workflow
```

## State Machine Updates

After digest is written:
- `applications.md` has new rows for every scored JD (state `evaluated` or `skip`)
- `output/jobs/` has new tailored artefacts for qualifying roles
- `reports/jobs/` has per-role evaluation reports

## Error Recovery

- Partial completion (Phase 4 crashed, Phases 1-3 done): re-running the routine with the same date argument should pick up from Phase 4 if intermediate JSON files exist.
- Full failure before Phase 7: digest.md should still be written with "PARTIAL RUN" status and a list of what completed.
- State pollution (applications.md row added for a role that failed tailoring): acceptable - the row stays `evaluated`, and user is notified via digest.

## Known Limitations

- Apple-style sites that block bots still require LinkedIn fallback (may degrade JD fidelity)
- Posting age often unknown from Greenhouse API; legitimacy flags `caution` default
- First few runs need threshold tuning - user feedback loop expected
- Cost scales with volume; 20+ survivors can push toward budget cap

## Success Criteria

Daily run succeeds when:
1. Digest file written (even if PARTIAL)
2. At least Phase 1 completed
3. No silent failures (every error logged to pipeline-log.md)
4. User can act on the digest within 10 minutes of reading it
