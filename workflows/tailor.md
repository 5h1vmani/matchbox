---
id: tailor-workflow
purpose: Reformulate the master CV for a specific JD using JD vocabulary, without inventing claims
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 2500_tokens
---

# Tailor Workflow

Reformulate the master CV for a specific job description using JD vocabulary, without inventing claims or skills not evidenced in the source CV.

## Priority Optimization: The First 500 / First 150 (added 2026-04-20)

Modern ATS (Ashby, Lever, Greenhouse v2) generate LLM-driven candidate summaries. Recruiters see these summaries BEFORE they open the full document. For a CV, the first ~500 words drive the summary. For a cover letter, the first ~150 words.

**Every tailor decision should optimize for this preview window first. Tail content matters less.**

- **CV first 500 words =** header + professional summary + core competencies + first 1-2 work experience entries.
- **Cover letter first 150 words =** opening paragraph.

These regions must contain: the role title verbatim, the top 5 JD keywords, the anchor fact (e.g., 250K CCU load test), and a role-specific positioning claim.

## Multi-Application Hygiene Rule (added 2026-04-20)

Before writing any cover letter, check `matchbox/people/{name}/applications.md` for other pending applications at the same company.

- **If the user has applied or is applying to >1 role at the same company in the same batch**, DROP all cross-reference language from every cover letter in that batch.
- Never write "my first preference is X" or similar language that would contradict a parallel application.
- Silent is better than stated preferences. The recruiter sees all applications via the ATS.

**Pilot learning (2026-04-20):** three initial cover letters had contradictory "first preference is X" lines. A recruiter reading all three would dismiss the candidate as spray-and-pray. The fix is to say nothing about other applications in the letter itself.

## Pre-requisites

- Score ≥ `mode.yml:thresholds.tailor_min`
- JD text available (from `score.md` output)
- Report written with extracted keywords
- `atma/people/shiva/wiki/cv.md` accessible

## Read Set (Atma Routing: cv_tailoring)

From `atma/people/{name}/routing.md`:

```yaml
always:    [cv.md, skills.md, projects.md]
sometimes: [story-bank.md, voice.md, narrative.md]
never:     [comp.md, network.md, preferences.md, log.md]
budget:    12000_tokens
```

## Procedure

### Step 1: Extract Keywords

15-20 keywords from the JD (these already exist in the report from `score.md`). Retrieve them from the report's "Keywords Extracted" section.

### Step 2: Map Keywords to CV

For each keyword, find an exact match in `cv.md` work bullets, skills section, or projects. If no map exists, note the gap. Do NOT invent skills or experience.

Create a mapping table:
- JD keyword → CV section → Evidence (exact quote from cv.md) → Exact match? (yes/no/partial)

### Step 3: Reformulate Mapped Bullets

Rewrite bullets to use JD vocabulary. Example: if CV says "LLM workflows with retrieval" and JD says "RAG pipelines", change the bullet to "RAG pipelines". Never add un-evidenced skills.

Rule: the claim must exist in the CV already; only the phrasing changes.

### Step 4: Reorder Work Experience Bullets

Reorder experience bullets by JD relevance. Place the most relevant role and bullets first.

### Step 5: Rewrite Professional Summary

Rewrite the Professional Summary (opening paragraph of CV) with top 5 JD keywords. Include a hook that bridges Shiva's stated exit story (from `narrative.md`) to the JD's problem space.

Max 4-5 sentences.

### Step 6: Select Top Projects

From `projects.md`, select the top 3-4 most relevant projects (by evidence of technical depth and business outcome). Emphasize projects that use JD vocabulary.

### Step 7: Apply AI Detection Checklist

Apply `atma/shared/ai-detection-guide.md` checklist (8 tells + pre-send checklist). Fix any detected AI markers.

### Step 8: Apply Voice Rules

Apply `atma/people/shiva/wiki/voice.md` rules:
- No em dashes
- No contractions ("do not" not "don't")
- No banned phrases (defined in voice.md)
- 3+ authenticity signals (specific metrics, dates, named collaborators)

### Step 9: Render to HTML (then PDF) — STRICT TEMPLATE ENFORCEMENT

**MANDATORY:** always load the shared template file and substitute placeholders. Do NOT generate HTML inline. Do NOT write your own CSS.

Steps:

1. **Load font config** from `atma/shared/fonts/font-config.yml`:
   - Read the profile's preferred font (from `atma/people/{name}/wiki/profile.yml:preferences.font`) OR fall back to `font-config.yml:active` (default `atkinson_hyperlegible`).
   - From `font-config.yml:fonts[{key}]` get: `name`, `files.regular`, `files.bold`, `css_font_family`.
2. **Base64-encode fonts**:
   - Read the regular .ttf file bytes, base64-encode, store as REGULAR_B64
   - Read the bold .ttf file bytes, base64-encode, store as BOLD_B64
3. **Load the template**:
   - CV: read `atma/shared/cv-template.html`
   - Cover letter: read `atma/shared/cover-letter-template.html`
4. **Substitute all placeholders** in the template:
   - `{{FONT_NAME}}` → the font's `name` (e.g., "Atkinson Hyperlegible")
   - `{{FONT_FAMILY}}` → the font's `css_font_family` (complete CSS stack)
   - `__REGULAR_B64__` → the base64 regular font
   - `__BOLD_B64__` → the base64 bold font
   - All content placeholders ({{NAME}}, {{SUMMARY}}, {{EXPERIENCE}}, etc.)
5. **Write output HTML** to `matchbox/people/{name}/output/jobs/{YYYY-MM-DD}/html/cv-{slug}.html` (HTML goes in an `html/` sub-folder; PDFs go in `pdfs/`)

### Step 9.5: Template-usage validation (MANDATORY, added 2026-04-20)

Before proceeding, verify the output actually used the template and fonts:

```bash
# Font family must be substituted (no raw placeholder left)
grep -c "{{FONT_FAMILY}}" {output.html}  # must be 0
grep -c "{{FONT_NAME}}" {output.html}    # must be 0
grep -c "__REGULAR_B64__" {output.html}  # must be 0
grep -c "__BOLD_B64__" {output.html}     # must be 0

# File must contain base64-embedded fonts (large file size)
# CV HTML with embedded Atkinson should be >150KB
# If <100KB, base64 fonts likely not embedded
python3 -c "import os; size = os.path.getsize('{output.html}'); assert size > 100_000, f'Template not used; file is only {size} bytes. Probably generated inline CSS without fonts.'"
```

If any check fails, REJECT the output. Return to Step 1. Common failure: agent generated HTML from scratch with inline CSS and system fonts. Re-run with explicit template loading.

**Pilot learning (2026-04-20):** scan-generated CVs came out 12KB with `-apple-system` fonts because the tailor agent generated HTML inline instead of using the template. Fonts were never embedded. This check prevents that regression.

### Step 9.5: MANDATORY Rendering Test (added 2026-04-20)

Generate PDF from the rendered HTML via headless Chrome. The PDF goes in the `pdfs/` sub-folder, alongside the `html/` sub-folder you just wrote to.

```bash
# Ensure the pdfs/ sub-folder exists
mkdir -p "matchbox/people/{name}/output/jobs/{YYYY-MM-DD}/pdfs"

# Render to PDF. Input is the html/ file; output goes to pdfs/
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf="matchbox/people/{name}/output/jobs/{YYYY-MM-DD}/pdfs/cv-{slug}.pdf" \
  "file://{absolute_path_to_html_file}"
```

Check page count using one of:
```bash
# Quick check via pdfinfo (if available)
pdfinfo "{output.pdf}" | awk '/Pages:/ {print $2}'

# Or via Python pypdf
python3 -c "from pypdf import PdfReader; print(len(PdfReader('{output.pdf}').pages))"
```

**Page count constraints (must pass):**

| Artifact | Required page count | Failure action |
|----------|---------------------|----------------|
| CV | Exactly 2 pages | Return to Step 8 (trim content or slightly tighten font/margins); never >2, never <1 |
| Cover letter | Exactly 1 page | Return to Step 8 (trim content); never >1 |

**Pilot learning (2026-04-20):** page-break CSS bugs produce 3-page CVs that silently pass voice lint. This test catches layout failures agents cannot self-detect.

### Step 9.6: MANDATORY Factual Audit (added 2026-04-20)

Run the 7-check factual audit defined in `matchbox/workflows/factual-audit.md`.

The audit catches:
- Present-tense customer claims ("I serve..." when not currently serving)
- Unsourced scale claims (bare "250K users" without "load-tested" qualifier)
- Removed or sensitive entity references (Apollo, Avinash as pilot customer, Campuzzz, Tara in tailored output)
- Tense violations ("for 100K students" implying real users)
- References to companies/tools not verifiable in master cv.md

**Do NOT skip. Agents have historically missed honesty violations even with full voice compliance.**

If factual audit returns any violations: return to Step 2 (keyword mapping) and rewrite the offending bullets with verified framings. Do NOT proceed.

### Step 10: MANDATORY Automated Lint (added 2026-04-20)

**Do NOT skip. Do NOT self-certify.** Run these checks against the rendered HTML file (not just the "content" the agent wrote — the full rendered file, including HTML comments, `<title>` tags, and project titles):

```bash
# Em dash check. Must be zero.
grep -c "—" {output_file_path}

# Contraction check. Must be zero.
grep -cE "(don't|doesn't|it's|we're|you're|I'm|haven't|won't|can't|aren't|isn't|didn't|wouldn't|shouldn't|couldn't|hasn't)" {output_file_path}

# Banned phrase check. Must be zero.
grep -ciE "(leverage|synergy|passionate about|game-changer|revolutionary|results-driven|spearhead|orchestrate)" {output_file_path}
```

If any check returns non-zero:
- Report the violations with line numbers
- Return to Step 6 (Voice compliance) and rewrite
- Do NOT mark the tailor as complete. Do NOT self-assert "PASS" without running these greps.

**Pilot learning (2026-04-20):** both Sonnet tailor agents claimed "voice compliance: PASS" while their outputs contained 14 and 11 em dashes respectively, in project titles, `<title>` tags, and self-check comments. Agent self-assessment is not reliable. Automated lint is the only honest check.

## Output

Date-scoped, two sub-folders:

```
matchbox/people/{name}/output/jobs/{YYYY-MM-DD}/
├── html/
│   ├── cv-{company-slug}-{role-slug}.html
│   └── cover-{company-slug}-{role-slug}.html
└── pdfs/
    ├── cv-{company-slug}-{role-slug}.pdf
    └── cover-{company-slug}-{role-slug}.pdf
```

**Why the split:** PDFs are the artefact you submit. HTML is source for debugging or hand-edits. Keeping them separate means the `pdfs/` folder is a clean list ready to upload; the `html/` folder is working state you can ignore unless something is wrong.

Also:
- Update `applications.md`: add PDF link pointing to `pdfs/` path
- Write `cv_path` and `cover_path` to the DB via `db.mark_tailored(...)` — both should point to the PDF paths in `pdfs/`
- Only after Step 10 lint passes.

## Cost Budget

~3K tokens per tailored CV.

## Failure Modes

- **JD has no keywords the CV can honestly match**, score was wrong or JD requirements are outside Shiva's profile. Do not invent claims. Flag for user review and consider downgrading recommendation in report.
- **Tailored CV reads AI**, voice rules violated or reformulation sounds generic. Rerun after re-reading `voice.md`. Check for common AI markers (hedging language, generic adjectives, missing specifics).
- **Bullets reordering loses narrative coherence**, original ordering had a story (e.g., progression from junior to senior, building one platform over time). Restore original sequence, reorder only top 2-3 most relevant bullets instead.
