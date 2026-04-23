---
id: matchbox-readme
purpose: What Matchbox is, how it relates to Atma, and the contract between them
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 2500_tokens
---

# Matchbox

Matchbox is a job pipeline tool. It scans for roles, scores them against your profile, tailors a CV for the ones worth applying to, and tracks the pipeline from evaluated to offer.

Matchbox does not store who you are. Atma does. Matchbox reads Atma and runs the search.

## The Two-Layer Architecture

```
atma/              ← identity layer (source of truth about you)
  shared/          ← scoring rubric, CV template, AI detection guide
  people/{name}/   ← wiki (profile, cv, skills, stories, voice, etc.)

matchbox/          ← pipeline layer (application state)
  shared/          ← pipeline states (states.yml)
  workflows/       ← scan, score, tailor, apply, interview prep
  people/{name}/   ← mode config, search queries, applications, reports, output
```

Atma is read-only to Matchbox, with one narrow write-back channel (ingest protocol).

## The Contract

| Direction | What | Mechanism |
|-----------|------|-----------|
| **Read** (atma → matchbox) | Identity files per task | Matchbox declares task (`job_scoring`, `cv_tailoring`, `interview_prep`); `atma/people/{name}/routing.md` returns allowed files |
| **Write** (matchbox → matchbox) | Pipeline state: applications, reports, tailored CVs | Direct writes to `matchbox/people/{name}/` |
| **Write-back** (matchbox → atma) | Events that change identity: applied, interview feedback, rejection reason, new story seed | Goes through `atma/shared/ingest-protocol.md` (the 5 questions); lands in `atma/people/{name}/wiki/log.md` |

Matchbox never writes to Atma directly. Always through ingest. Deny wins on sensitivity tiers.

## The Modes

Matchbox has three operating modes, controlled by `people/{name}/mode.yml`:

| Mode | Scan | Tailor threshold | Surface threshold | External signal | Hours/week |
|------|------|-----------------|-------------------|-----------------|-----------|
| **passive** | weekly | ≥ 4.0 | ≥ 4.5 | zero | ~15 min |
| **warm** | daily | ≥ 3.5 | ≥ 4.0 | minor (selective apply) | 1-3 |
| **active** | 2x daily | ≥ 3.5 | ≥ 4.0 real-time | loud (LinkedIn open) | 15-25 |

Switching modes is one file edit. See `people/{name}/mode.yml`.

## The Five-Phase Funnel

Every scan runs the same funnel. Cost decreases dramatically for jobs that drop out early, so the top is cheap and the bottom is expensive.

1. **DISCOVER**, web search queries from `search-queries.yml`. ~100 tokens/query. Returns titles + companies + snippets.
2. **DEDUP**, normalize (company + title) against `applications.md`. Zero extra tokens.
3. **FETCH**, retrieve full JD only for survivors. ~200-500 tokens/job (API preferred over HTML).
4. **SCORE**, apply `atma/shared/scoring-rubric.md` using files from Atma's `job_scoring` routing. ~1K tokens/job.
5. **TAILOR**, for jobs scoring ≥ `mode.yml:thresholds.tailor_min`, reformulate the CV via `atma/shared/cv-template.html` and `ai-detection-guide.md`. ~3K tokens/job.

See `workflows/scan.md` for the full mechanics.

## Directory Layout

```
matchbox/
├── README.md                       this file
├── shared/
│   └── states.yml                  canonical pipeline state machine
├── workflows/
│   ├── scan.md                     5-phase funnel, dedup, legitimacy check
│   ├── score.md                    applying the rubric, report format
│   ├── tailor.md                   CV reformulation + AI detection
│   ├── apply.md                    submission + writeback to Atma
│   └── interview-prep.md           research + STAR+R mapping
└── people/{name}/
    ├── mode.yml                    current operating mode + thresholds
    ├── search-queries.yml          role targets + dream companies + platforms
    ├── applications.md             pipeline tracker (states.yml compliant)
    ├── reports/                    one evaluation report per scored opportunity
    └── output/                     tailored CVs (HTML + PDF) per application
```

## Engineering Principles

- **SSOT**: Atma owns identity; Matchbox owns pipeline. Nothing is duplicated. `scoring-rubric.md`, `cv-template.html`, and `ai-detection-guide.md` live in `atma/shared/`, referenced never copied.
- **DRY**: `search-queries.yml` is generated from `atma/people/{name}/wiki/profile.yml` (title_filters, keywords, dream_companies). Editing the profile updates scans automatically.
- **Single responsibility**: each workflow file encodes one verb. Each per-person file has one purpose.
- **Least privilege**: routing contracts between Atma and Matchbox enforce read boundaries. Matchbox cannot read `comp.md` or `network.md` unless the task routing permits.
- **Fail closed**: unknown tasks return empty. Missing frontmatter makes a file invisible. Default deny.
- **Auditability**: every write-back to Atma goes through the ingest protocol's 5 questions. Every scan logs its query set to `reports/scan-history.tsv` (not implemented in v1; add when volume justifies).

## How to Use

### First-time setup
1. Create `people/{name}/` folder with `mode.yml` and `search-queries.yml` (once per user).
2. Initialize empty `applications.md` with the states.yml header.
3. Confirm Atma routing allows the tasks Matchbox will call.

### Daily run (warm mode)
1. User: "Run scan."
2. Matchbox executes the 5-phase funnel.
3. Returns a digest: new hits, top scores, tailored CVs ready.
4. User reviews, decides which to apply, triggers apply workflow.
5. Apply workflow writes to `applications.md` and write-backs to Atma `log.md`.

### When an interview comes up
1. User: "Prep for interview at {company}."
2. Matchbox reads `atma/people/{name}/wiki/` (interview_prep routing) + runs research queries.
3. Returns round-by-round breakdown + STAR+R story mapping + prep checklist.

## What's Not in v1

- Automated application submission (always manual; prevents spray-and-pray)
- Recruiter outreach automation
- Multi-person orchestration (each user has their own folder; no cross-user queries)
- Analytics dashboard (applications.md is enough until >100 apps)
- Email/calendar integration
