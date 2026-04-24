---
id: scan-funding-news
purpose: Discover recently-funded AI companies (Series A-C, last 6 months, ≥ $10M) from news sweeps and add qualifying ones to well-funded-watchlist.yml. Populates tier_4_exploratory.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-21
review_by: 2026-10-21
size_budget: 2500_tokens
---

# Scan Funding News Workflow

Weekly-cadence discovery job. Uses search queries over news sites to find companies that raised recently, passes them through a filter, writes qualifying rows into `matchbox/people/{profile}/well-funded-watchlist.yml`. Does NOT score jobs — that happens in the standard daily/marathon scans, which read the watchlist downstream via `mode_5_funded_recent`.

## Invocation

- Claude Code: `/scan-funding-news --profile shiva` (not currently registered; add as slash command if desired)
- Any Sonnet session: paste this workflow + say "run for profile shiva"
- OS cron (recommended): `0 9 * * 1 cd {repo} && <invoke this workflow for profile shiva>` — weekly, Monday morning

## Pre-requisites

- `matchbox/people/{profile}/search-queries-jobs.yml:funded_recent_queries.discovery_news` present
- `matchbox/people/{profile}/well-funded-watchlist.yml` exists (scaffolded empty is fine)
- `atma/people/{profile}/wiki/profile.yml:dream_tiers` populated (for dedup: do not add a company that is already tier_1/2/3)

## Procedure

### Step 1 — Load context

1. Run `matchbox/workflows/profile-dispatcher.md` with the provided arguments.
2. Read `matchbox/people/{profile}/well-funded-watchlist.yml`. Collect existing company names into a set `known_watchlist`.
3. Read `atma/people/{profile}/wiki/profile.yml:dream_tiers`. Collect names from tier_1_dream + tier_2_target + tier_3_watchlist into a set `known_dream`.
4. Read `atma/people/{profile}/wiki/profile.yml:exclusions` — each sector's global_default. Use for Step 3 filtering.

### Step 2 — Run discovery queries (Haiku)

Execute each query in `search-queries-jobs.yml:funded_recent_queries.discovery_news`. For each hit, extract:

- `company`
- `stage` (Series A / B / C)
- `amount_usd` (e.g., "15M")
- `lead_investor` (if mentioned)
- `source_url`
- `source` (e.g., "techcrunch-2026-04-18")
- `announcement_date` (YYYY-MM-DD)
- `brief_description` (what the company does, one sentence)
- `sector` (one of: ai_tooling, ai_application, ai_infra, ml_platform, dev_tools, foundation_model, enterprise_ai, consumer_ai, other)

Budget: 3-5K tokens for discovery. Run queries serially; stop early if 30 unique companies are collected.

### Step 3 — Filter candidates (aggressive, free, in-Python)

Reject a candidate if ANY of:

1. **Already known**: company name in `known_watchlist` ∪ `known_dream` (case-insensitive match). Skip silently — already on the radar.
2. **Stale funding**: `announcement_date` > 6 months ago from today.
3. **Too small**: `amount_usd` < $10M (strip "M", parse float; if the raise is in a different currency, convert rough to USD). Configurable via `profiles.yml:funded_recent.amount_floor_usd`.
4. **Stage below threshold**: stage not in {Series A, Series B, Series C, Series D}. Seed / pre-seed / bridge rounds rarely fund FDE/SA hiring.
5. **Sector excluded**: sector matches any key in `profile.yml:exclusions` where `global_default: exclude` AND the company is NOT headquartered in an overridden country. Mark `excluded_reason: "{sector}|{country}"`.
6. **Non-AI**: sector is not one of the AI categories (ai_tooling, ai_application, ai_infra, ml_platform, dev_tools, foundation_model, enterprise_ai, consumer_ai).
7. **No hiring signal in description**: `brief_description` contains no word that suggests the company is product-building (deployment, engineering, solutions, customer, applied, product, research, infrastructure, platform, agents). Too passive a sector to be hiring.

Keep a parallel list `rejected` with `{company, reason}` for the digest.

### Step 4 — Hiring-signal check (prevents dead leads before watchlist write)

For each survivor, verify they are ACTIVELY HIRING before writing to watchlist:

1. **Find careers URL**: run ONE targeted query like `"{company} careers"` OR read the company's homepage `/careers` path. Prefer the structured answer.

2. **Detect ATS platform**: pattern-match the URL:
   - Contains `jobs.ashbyhq.com/{slug}` → `ats_platform: ashby`, extract slug
   - Contains `jobs.lever.co/{slug}` → `ats_platform: lever`, extract slug
   - Contains `boards.greenhouse.io/{slug}` or `{slug}.greenhouse.io` → `ats_platform: greenhouse`, extract slug
   - Contains `careers.{domain}` or custom subdomain → `ats_platform: custom`
   - Otherwise → `ats_platform: unknown`

3. **Verify ≥ 1 open role**:
   - If `ats_platform` is ashby/lever/greenhouse, hit the public API endpoint from `search-queries-jobs.yml:funded_recent_queries.ats_api_templates`. Count roles returned. Must be ≥ 1.
   - If `ats_platform` is custom/unknown, HEAD-check the careers URL. Must return 200. Fetch once and look for `"hiring"`, `"open positions"`, `"join us"` text (Haiku can confirm in one cheap call).
   - If the page 404s, or the API returns empty, or no hiring language is found: **do not add to watchlist**. Log as `rejected: no_hiring_signal`.

4. **Record open-role count**: set `roles_seen_at_discovery: N` on the watchlist entry. Used later for dormancy tracking.

Companies that pass Stage 4 are real, funded, AI, hiring, and in an allowed sector. Only those get written.

### Step 5 — Write to watchlist

Append each survivor to `watchlist:` in `well-funded-watchlist.yml` with this shape:

```yaml
- company: {name}
  stage: {Series X}
  amount_usd: {N}M
  lead_investor: {name or null}
  source: {source-slug}
  source_url: {url}
  discovered_date: {today YYYY-MM-DD}
  ttl_expires: {today + 6 months}
  sector: {categorized}
  brief_description: {one sentence}
  careers_url: {url or null}
  ats_platform: {ashby | lever | greenhouse | custom | unknown}
  roles_seen: []          # daily scan populates as it finds jobs
  high_scoring_jobs: 0    # count of roles scored ≥ 4.0 within TTL window
  promotion_candidate: false
  notes: {1-line context}
```

Use `yaml.safe_dump` via a Python helper to avoid hand-formatting errors. Preserve existing entries in the file; do not overwrite.

### Step 6 — Digest

Write `matchbox/people/{profile}/runs/{YYYY-MM-DD}-funding-news/digest.md`:

```markdown
# Funding News Scan — {date}

## Summary
- Discovery queries run: {N}
- Raw candidates: {N}
- Filtered to survivors: {N}
- Added to watchlist: {N}

## Added (this run)
| Company | Stage | Amount | Sector | Careers |
|---|---|---|---|---|
| ... |

## Rejected (this run)
| Company | Reason |
|---|---|
| ... |

## Current watchlist size
- Active: {N} (not expired)
- Expired: {N} (dropped this run)
- Promotion candidates: {N} (≥ 2 high-scoring jobs)
```

### Step 7 — TTL + dormancy housekeeping (run every sweep)

Load the existing watchlist. Apply three rules in order:

**Rule 1 — Expired TTL:**
- Any entry where `ttl_expires < today`:
  - If `high_scoring_jobs >= 1` → extend `ttl_expires` by 3 months (earned more time).
  - Else → move to `archive:` with note `"TTL expired, no high-scoring roles"`.

**Rule 2 — Dead careers page (added 2026-04-21):**
- Any entry where `url_last_checked` on the careers URL shows 4xx for 3+ consecutive daily checks:
  - Move to `archive:` with note `"careers page dead ({status}) since {date}"`.
  - This data comes from the daily scan's HEAD-check loop (see `daily-scan-jobs.md`).

**Rule 3 — Dormant (added 2026-04-21):**
- Any entry where `roles_seen` has grown by 0 over the last 90 days (no new roles discovered from their careers page):
  - Move to `archive:` with note `"dormant: zero new roles in 90d"`.
  - Company is real but not hiring anymore; holding them wastes daily scan cost.

**Rule 4 — Promotion candidate:**
- Any entry with `high_scoring_jobs >= 2` and `promotion_candidate != true`:
  - Set `promotion_candidate: true`.
  - List in the digest for user review.
  - User decides whether to manually graduate to `profile.yml:dream_tiers.tier_3_watchlist`.

**Watchlist cap (added 2026-04-21):**
Active watchlist capped at 100 entries. If a sweep would push over the cap, drop the oldest entries with `roles_seen == 0` first. Prevents the watchlist from becoming a zombie list.

## Cost Budget

~5K tokens per weekly run (mostly Haiku). Roughly $0.05-$0.10. Low-frequency; negligible in the monthly envelope.

## Outputs

- Updated `matchbox/people/{profile}/well-funded-watchlist.yml`
- Digest at `matchbox/people/{profile}/runs/{date}-funding-news/digest.md`
- Scan_run row via `db.create_scan_run(profile, mode="funded_recent_news", country="global")` + `db.complete_scan_run(...)` for auditability

## Failure Modes

- **Discovery returns zero hits**: news sites may have rate-limited. Try again in an hour or switch to Crunchbase API (not yet wired).
- **Watchlist file corrupted**: back it up, load the last known-good from `runs/{prev-date}-funding-news/`, prompt user.
- **Duplicate companies in a single run**: dedup in-process by lowercase company name before writing.
