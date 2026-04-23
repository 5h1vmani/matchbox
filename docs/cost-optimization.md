# Cost Optimization — Pipeline Analysis

**Date:** 2026-04-21
**Scope:** Funding-news scan + Tailor batch (the two production pipelines).
**Not in scope:** strategy discussions, one-off UI changes, conversational refinements.

This doc decouples the two pipelines we ran today, identifies where LLM spend was wasted, and proposes a concrete refactor plan to get the same (or better) quality at ~5x lower cost.

## The single meta-principle

**LLM for judgment. Code for transformation.**

Every time a pipeline run was slow or expensive, the root cause was the same: an LLM was doing string substitution, file I/O, or regex work that Python does for free. Every retry loop was LLM regenerating content that did not need to change.

Today's tailor batch breakdown:
- ~20% of the work was judgment (bullet rewriting, summary prose, cover letter arc, voice-sensitive reasoning)
- ~80% was mechanical (template substitution, base64 font embed, HTML emit, page count, grep-based lint, Chrome render, DB write)

We paid LLM pricing for 100% of it. If we only paid LLM for the 20%, the batch would cost ~5x less at the same quality.

---

## Pipeline 1 — Funding-news scan

### What it does today
Discovers recently-funded AI companies via search queries, filters/dedupes, probes their careers pages, scores matching jobs, writes to DB.

### Today's spend profile (approximate)

| Step | Tool | Tokens / calls | Notes |
|---|---|---:|---|
| Discovery queries (11) | WebSearch | ~60K | Each query returns snippets; Python parses |
| Filter against known set | Python | 0 LLM | Free |
| ATS API probes (14 companies, ~20 slugs tried) | curl via Bash | 0 LLM | Free |
| Job extraction + location normalization | Python | 0 LLM | Free |
| Title + country filtering | Python | 0 LLM | Free |
| Scoring 63 jobs (6-dim rubric) | Sonnet (inline) | ~100K | My own reasoning |
| Report generation (stub markdown per job) | Python | 0 LLM | Free |
| DB batch writes | Python + db.py | 0 LLM | Free |
| Watchlist update | Python YAML | 0 LLM | Free |

**Rough total: ~160K tokens. This pipeline is already efficient.**

### Redundancies found

1. **Duplicate JSON serialization between phases.** Phase 1 writes `phase-1-discovery.json`, Phase 2 reads it and writes `phase-2-filtered.json`, etc. Each step re-packs the same rows. Tokens are not burnt here (Python is free) but disk I/O and cognitive load increase with every step.

2. **Haiku agent for 7-company careers URL hunt** returned mixed-quality results (4 correct slugs, 3 wrong). The cheap mistake was trusting the agent's "confidence: high" tags without re-probing. Fix: always re-probe after Haiku-suggested slugs.

3. **No prompt caching on scoring.** I scored jobs one company at a time by loading the profile + rubric into context each time. If scoring were dispatched as a sub-agent with a stable prefix (profile + rubric + master CV) and variable JD text at the end, prompt caching would cut input cost ~10x on the 2nd through Nth job.

### Improvements for this pipeline

**A. Move scoring to a structured function.** Replace my inline reasoning with a small Sonnet call that takes `(profile.yaml, rubric.yaml, role_family, job_dict)` and returns `{cv_match, company_mission_fit, role_mission_fit, comp, cultural, red_flags, total, recommendation, role_family, evidence: {...}}`. One prompt schema, one Haiku-or-Sonnet call per job, prompt-cached prefix.

**B. Add smart-slug ATS probe.** When initial slug probes miss, before delegating to Haiku: try 3-5 more algorithmic variants (hyphenated, no-spaces, `-ai` stripped, `labs` stripped, etc.). Haiku agent only for the truly ambiguous ones.

**C. Cache ATS JSON responses.** A single Greenhouse or Ashby API response can list 50-200 jobs. Persist these JSONs to disk keyed by slug + date. The daily scan does not re-fetch when a company's data is < 24h old.

**D. Cost estimate per company pre-flight.** Before the enrichment step, estimate cost for each candidate. If the batch is going to exceed budget, rank-cut lower-score candidates first.

---

## Pipeline 2 — Tailor batch (the expensive one)

### What it does today
Takes N queued jobs. For each, produces a tailored CV (+ optional cover letter) by running the 10-step workflow: extract JD keywords, map to CV, reformulate bullets, rewrite summary, select projects, load HTML template, substitute placeholders, base64-encode fonts, render HTML, Chrome → PDF, run 4 quality gates.

### Today's spend profile

| Step | Where | Approximate tokens (per job) | Notes |
|---|---|---:|---|
| Agent reads shared files | Each agent independently | ~30K | Same 10-14 files, read 22 times |
| Keyword extraction | LLM inside agent | ~2K | Should be Haiku |
| Bullet reformulation | LLM inside agent | ~5K | Real reasoning work |
| Summary rewrite | LLM inside agent | ~2K | Real reasoning |
| Template load + base64 fonts | LLM inside agent | ~50K-200K | Should be Python |
| HTML output (300KB per CV, base64 fonts embedded) | LLM output | ~200K | Should be Python |
| 4 quality gates | LLM interpreting shell output | ~5K-10K | Should be Python |
| Chrome render + page count check | shell, interpreted by LLM | ~2K | Should be Python |
| Retry loops (when page count failed) | LLM regenerates full HTML | up to 200K extra | Root cause: can't do surgical edits on HTML |

**Average per job: ~100K tokens. 22 tailor agents (20 jobs + 2 retries) = ~2.2M tokens.**

At Opus sub-agent pricing this would be ~$45-70. At Sonnet ~$10-15. Either way, well above my estimate of "$10-12 total".

### Redundancies found

1. **Shared file reads replicated 22 times.** cv.md, voice.md, template.html, ai-detection-guide.md, tailor.md, factual-audit.md, skills.md, projects.md, story-bank.md, narrative.md, font-config.yml, 2 font binaries. Each agent read them independently. 22 × 30K = 660K tokens of pure replay.

2. **HTML regeneration per retry.** When a CV came out at 3 pages, the agent regenerated the entire ~300KB HTML file (including 200KB of base64 fonts) to change 2 bullet lines. Each retry burned ~50-70K output tokens to emit content that did not change.

3. **Template + base64 fonts in the LLM output path.** The LLM was emitting ~200KB of base64-encoded font bytes in its output stream for every CV. The fonts are identical across all 20 CVs and the 11 cover letters. This should be a Python `file.write(base64.b64encode(font_bytes))` call, not LLM output.

4. **Brief replication by copy-paste.** I wrote 22 near-identical 2-3K-token briefs. Only ~500 tokens per brief were job-specific (role title, paths, company anchors). The rest was shared boilerplate.

5. **Quality gates inside the LLM.** Each agent ran grep commands and parsed their output inside its context. Gate logic is deterministic: `grep -c "—" file.html` returns 0 or a positive integer. Python can check that in 1 line; the LLM was doing it in ~5K tokens.

6. **Factual error propagation across agents.** The "four years at NTT DATA" error (correct: two years) was in my first ~15 briefs before an agent caught it against `cv.md`. Every upstream CV may carry the wrong phrasing. No pre-flight fact check caught this.

7. **ElevenLabs #14 report missing.** The queue had a job whose `report_path` did not exist on disk. Caught at dispatch time, not at pre-flight. I had to generate a stub report mid-run.

### Improvements — cost leverage (>5x savings)

**A. Content-as-JSON (biggest single win).**
Instead of the agent producing a 300KB HTML file, it produces a structured JSON content dict:

```json
{
  "professional_summary": "...",
  "experience": [
    {"role": "...", "company": "...", "dates": "...", "bullets": ["...", "..."]}
  ],
  "projects": [...],
  "skills_selected": [...],
  "keywords_used": [...],
  "tailoring_notes": "..."
}
```

Maybe 3K tokens of output per job. A separate Python script does the template substitution, base64 font embed, HTML emit, Chrome render, page count check, voice lint, factual audit regex. Zero LLM cost on the mechanical part.

Savings: ~80% of output tokens, which is the expensive axis (output is 5x input price).

**B. Prompt caching on the shared prefix.**
Structure every agent's prompt so the identical ~30K tokens of shared reads (cv.md, voice.md, template.html, ai-detection-guide.md) are the very first block, verbatim, byte-for-byte identical across agents. Anthropic's prompt cache kicks in and agents 2-N pay ~10% of input cost on the cached portion.

Savings: ~70-90% of input cost on the shared portion, across all agents after the first.

**C. Single-orchestrator loop instead of N isolated agents.**
One long-running session reads shared files once (~30K tokens). Then iterates through N jobs, producing one content dict per job with prior context retained. Per-job output ~10K tokens. Total: 30K + N × 10K.

For N=20: 30K + 200K = 230K tokens, vs 2.2M for the 20-isolated-agents approach. **~90% cost reduction.** Tradeoff: serial wall clock ~60 min vs parallel ~15 min.

**D. Haiku for mechanical LLM steps.**
- Keyword extraction from JD: Haiku
- Regex-friendly factual checks: Haiku or none
- Voice lint: pure shell (no LLM)
- Page count: pure Python (pypdf)
- Role family classification: Haiku with a tight output schema

Sonnet only for: bullet reformulation, summary prose, cover letter narrative arc, red-flag assessment, anything requiring judgment.

Savings: ~50% on cheap steps, which scales with batch size.

### Improvements — quality leverage (better output, same or lower cost)

**E. Master CV as structured YAML.**
Convert `cv.md` to `cv.yaml` with structured work entries, skills, projects, each tagged. Example:

```yaml
work:
  - company: NTT DATA London
    role: Senior Associate — Finance Transformation
    tenure: 2 years
    dates: 2022-06 to 2024-06
    location: London, UK
    tags: [enterprise, sap-analytics, post-merger, europe, stakeholder-training, finance]
    bullets:
      - text: "Led the migration of 30 entities across Europe from Excel-based reporting to SAP Analytics Cloud."
        tags: [platform-migration, scale, enterprise]
        voice_verified: true
      - text: "Trained 150+ analysts and controllers on the new platform across London, Frankfurt, Munich, Prague."
        tags: [training, stakeholder, europe]
        voice_verified: true
      - text: "..."
```

Tailor-time work becomes: parse JD keywords → filter bullets whose tags match → pick top 3-4 per work entry → render. Deterministic. No LLM rewriting needed for the bullet selection step.

**F. Pre-baked voice-compliant bullet pool.**
Each work entry has 5-8 variant phrasings of each bullet, all pre-verified voice-clean (no em dashes, no contractions, no banned words). At tailor time, the agent picks which variants fit the JD vocabulary. No runtime rewriting = no voice risk = no retry loops.

**G. LLM-as-judge for gates.**
Instead of grep alone for factual audit, run one tight Sonnet call: "Does this CV claim Pinaka has real users? Does it mention Avinash/Apollo/Tara as current customers? Return JSON with pass/fail per check + line numbers." Catches semantic violations grep misses. Cheap (~$0.05 per CV) because output is tiny.

**H. Job clustering before tailoring.**
Cluster queued jobs by (role_family, company_tier). For a cluster of 4 Deepgram SA roles, generate ONE shared SA-voice scaffold (summary, experience ordering, project selection). Per-job specialization is just (URL, location, cover-letter-specific opener). Reuses 80% of reasoning across the cluster.

**I. Few-shot from past wins.**
Every tailored CV you approve becomes a few-shot example in the next batch's context. Pattern-match beats from-scratch generation: both cheaper and more consistent.

### Improvements — speed leverage

**J. Parallelize I/O, serialize judgment.**
- 20 WebFetch calls for JD content: parallel (I/O bound)
- 20 keyword extractions: batch into 1 Haiku call
- Cover letter drafting: can be parallel since each is independent
- Rubric scoring: already inlined in my context

**K. Long-lived Chrome process.**
Instead of spawning Chrome N times with unique `--user-data-dir`, run `chrome --remote-debugging-port=9222` once and send N "print URL to PDF" commands. Startup cost amortized.

**L. Word-count before render.**
Count words in the tailored content before running Chrome. If > ~750 words, trim first. Skips the "render → count pages → re-render" loop in 80% of cases.

### Improvements — discipline (process/infra)

**M. Budget-gated dispatch.**
Every agent call gets a `max_output_tokens` cap tied to expected output. If hit, return partial. No runaway retry loops.

**N. Real-time unit-cost tracking.**
After each agent returns, compute $spend from the `total_tokens` field. Abort batch if running at 2x projected unit cost. (I did not do this today; surprise was the direct result.)

**O. JSON schema contract.**
Every agent MUST return JSON matching a pre-declared schema. If it doesn't, fail fast, retry once with a strict reminder, then hard fail. Prevents the "agent produces prose explanations instead of structured output" drift.

**P. Pre-flight fact verification.**
Before dispatching ANY tailor agent, verify critical facts in the brief against `cv.md`. Specifically: tenure at each named company, specific numbers (250K CCU, 150+ users, 30 entities), project names. Catch errors before they propagate across 20 agents.

**Q. Pre-flight report-path existence.**
For every queued job, verify the `report_path` file exists on disk. If missing, regenerate a stub from the DB row OR skip with a flag. Do this in pre-flight, not mid-run.

---

## Concrete refactor plan

Priority order by return on effort:

### Step 1 — Content-as-JSON refactor (~4 hours, biggest saving)
Build three Python files:

- `matchbox/shared/tailor_content.py` — takes `(cv.yaml, rubric.yaml, report.md, job_dict)`, makes ONE Sonnet call, returns content dict conforming to JSON schema.
- `matchbox/shared/render.py` — takes `(content_dict, template.html, fonts/)`, produces `(rendered.html, rendered.pdf)`. Deterministic. Zero LLM cost.
- `matchbox/shared/gates.py` — takes `(html, pdf)`, runs all 4 gates as Python functions, returns `{pass: bool, violations: [...]}`. Zero LLM cost.

### Step 2 — Convert `cv.md` to `cv.yaml` (~2 hours, one-time)
Structured work entries with tags. Enables deterministic bullet selection. Also forces the "NTT DATA tenure = 2 years" fact to live in one place.

### Step 3 — Batch orchestrator (~1 hour)
Replace the `/tailor --batch` slash command and the `matchbox/workflows/tailor.md` procedure with a Python-orchestrated loop:

```
for job in queue:
    content = tailor_content(cv_yaml, rubric, report, job)     # LLM call, cheap
    html, pdf = render(content, template, fonts)                # Python, free
    gate_result = gates(html, pdf)                              # Python, free
    if gate_result.pass:
        db.mark_tailored(profile, job.id, cv_path=pdf, ...)
    else:
        retry_with_trim(content, gate_result.violations)        # LLM call on a JSON patch, cheap
```

### Step 4 — Prompt caching on shared prefix (~30 min)
When the tailor content function builds its prompt, put the stable parts first: cv.yaml, voice.yaml, ai-detection-guide.md. Job-specific bits (the JD, the report) go at the end. Across N jobs in a batch, prompt cache kicks in.

### Step 5 — Cost observability (~1 hour)
Add `matchbox/shared/cost_tracker.py` that logs each LLM call's `input_tokens` and `output_tokens` to a CSV per scan-run. Running total visible in UI. Abort if running total > `profiles.yml:tailor_batch_cap_usd`.

### Step 6 — Pre-flight checks (~1 hour)
Extend the `tailor --batch` pre-flight to:
- Verify every queued job's `report_path` exists; stub-regenerate if missing
- Verify key facts in `cv.yaml` (tenures, metrics) haven't changed since last batch
- Estimate batch cost from N jobs × average-per-job and compare to budget
- List multi-app companies and confirm hygiene flags are set

### Effort vs saving

Total build time: ~10 hours. Payback: after 2-3 tailor batches.

### Expected outcome

With the refactor:

| Metric | Today's batch (22 agents) | After refactor |
|---|---:|---:|
| LLM tokens | ~2.2M | ~250K |
| Estimated cost (Sonnet sub-agents) | $10-15 | $2-3 |
| Estimated cost (Opus sub-agents) | $45-70 | $8-12 |
| Wall clock | ~80 min (with parallelism) | 45-60 min (serial, but one process) |
| Quality gates | LLM-interpreted | Python-deterministic, more reliable |
| Retry cost | LLM regenerates full HTML | LLM regenerates only changed bullets |
| Factual-error propagation | Possible (happened today) | Blocked by pre-flight |

---

## When to revisit this document

- After each production tailor batch, update the "Today's spend profile" table in Pipeline 2 with actual tokens used.
- When switching models (e.g., Opus → Sonnet for orchestrator), recalibrate the "Estimated cost" tables.
- Quarterly: audit which optimizations have been implemented and which remain.

**Review by:** 2026-07-21 (three months).
