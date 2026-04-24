---
id: factual-audit
purpose: Deterministic honesty check on tailored CVs and cover letters before submission. Catches overclaim, false tense, unsourced scale, removed entities.
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-20
review_by: 2026-10-20
size_budget: 2500_tokens
---

# Factual Audit

Voice lint and AI-detection lint check STYLE. This workflow checks TRUTH. Run between Step 9 (render) and Step 10 (final lint) of `tailor.md`. Fails the run on any violation; agent must fix or the output is rejected.

Why this is separate from voice lint: agents that pass voice rules can still write present-tense user claims ("I serve coaching centers"), implied-scale claims ("Pinaka handles 250K users"), or references to removed entities (Apollo, Avinash as pilots, Campuzzz, Tara). Those are honesty failures, not style failures.

## Inputs

- Target file: the tailored HTML CV or cover letter
- Source of truth: `atma/people/{name}/wiki/cv.md` plus `atma/people/{name}/wiki/profile.yml`
- Honesty rules file: this document

## The Seven Checks

### Check 1: Present-tense customer claims

Flag any present-tense assertion of serving customers the candidate does not actually serve.

Patterns to flag (regex, case-insensitive):
```
I serve\b
\bserves [^.]*customers
\bhandles \d+
\bruns \d+ (concurrent|users|customers)
I held \d+
```

Rule: numbers implying real users without "load-tested," "target," or "simulated" context are presumed false unless verifiable via `atma/people/{name}/wiki/traction.md`.

Example violations:
- "I serve coaching centers in Tier-2 India" (false if pivoted away)
- "Pinaka handles 250,000 concurrent users" (false if pre-launch)
- "runs 100,000 students" (false if load test only)

Example valid framings:
- "load-tested Pinaka to 250,000 concurrent users with K6"
- "designed for 100K concurrent user capacity"
- "K6 stress-tested at 250K CCU"

### Check 2: Unsourced scale claims

Flag any large number (>100) in a customer/user context that lacks a qualifier.

Patterns:
```
\b\d+K CCU(?! (load|test|simulated|capacity))
\b\d+,\d+ (users|students|customers)(?! (load-tested|target|simulated|at .+ scale))
```

Rule: every scale claim must name either the mechanism (load-tested / simulated) OR context (at N scale / for N capacity).

### Check 3: Removed or sensitive entity references

Read current `cv.md` and profile state. Flag any mention of:
- Removed/pivoted entities: Apollo MedSkills, Avinash College of Commerce (as pilot customer only, not as education), Campuzzz (should only be in master cv.md, not tailored outputs for Anthropic)
- Unshipped products: Tara (idea, not shipped)
- Dead links or endpoints: ashby anthropic URL (confirmed dead; should be greenhouse)

Lookup: the entities-to-flag list lives in `atma/people/{name}/wiki/preferences.md` under `hide_from_cv` or can be maintained in this file's appendix.

### Check 4: Present-tense product claims that are future-tense

Flag tensing of currently-ideated or pre-launch work as if shipped.

Patterns to detect:
- "shipped Kubera" (Kubera is private, not publicly shipped)
- "launched Pinaka" (still pre-beta for most applications)
- Use of definitive past tense where the product is only built for internal use

Rule: use "built," "developed," or "load-tested" for pre-launch. Use "shipped" only for publicly released artifacts (Usepaso on npm and PyPI qualifies).

### Check 4b: Private-repo public-access claims (added 2026-04-20)

Projects marked as private repo in `atma/people/{name}/wiki/projects.md` (e.g., Pinaka, Kubera, Vasapitta) must not be referenced as publicly accessible.

Patterns to flag (case-insensitive):
- "link(s) in the (Pinaka|Kubera|Vasapitta) README"
- "the (Pinaka|Kubera|Vasapitta) README"
- "(Pinaka|Kubera|Vasapitta) is live at"
- "platform is live at" when followed by reference to a private project
- "github.com/5h1vmani/pinaka" or any direct repo URL for private projects
- "public repo" when applied to a private project

Rule: for private projects, say either:
- "I can walk through the architecture in a working session"
- "not public; happy to share in interview"
- "[project] is private; I can describe the stack and decisions in detail"

Only `Usepaso` is public (npm + PyPI, Apache 2.0). Only it can be referenced with "shipped," "available at," or "search for" language.

Example violation (found in pilot, 2026-04-20):
> "The platform is live at the links in the Pinaka README."

Example valid framing:
> "Usepaso is public at npm and PyPI. Pinaka and Kubera are private; I can walk through the architecture and shipped code in a working session."

### Check 5: Date implication violations

Flag phrases like "for 100K students" that imply real users when the mechanism was a load test.

Patterns:
```
for \d+K students
for \d+,\d+ students
across \d+,\d+ users
```

Rule: replace with "at N student scale" or "at N-user scale" to preserve the capability claim without implying real customers.

### Check 6: Company / customer / tool references must be verifiable

For every company, customer, or tool named in the tailored document:
- Check it appears in `cv.md` work experience, OR
- Check it appears in `projects.md` as a named project, OR
- Check it appears in a `writing-samples/` file

Flag any unnamed or unverifiable reference.

Example: if the tailored CV says "at Deltabase I delivered 42+ reports," confirm Deltabase is in cv.md work experience with matching metric.

### Check 7: Numerical consistency across the batch

If the candidate is applying to multiple roles with tailored CVs in the same session:
- Check that the same metric is stated with the same number across all CVs.
- Example: if Mumbai CV says "load-tested to 250K CCU" and Bengaluru CV says "load-tested to 300K CCU," that is a contradiction. Flag for human review.

## Output Format

```
FACTUAL AUDIT REPORT - {date}

Target file: {path}
Status: PASS | FAIL

If FAIL, list violations:

1. [Check N] Violation: "{exact quote from file}"
   Location: line {N}
   Rule violated: {which rule}
   Suggested fix: {what to change it to}

2. ...

If PASS:
All 7 checks cleared. Safe to proceed to final lint.
```

## Integration with Tailor Workflow

`tailor.md` calls factual-audit as Step 9.6 (between render and final lint):

```
Step 9:   Render HTML via template
Step 9.5: Rendering test (PDF page count)
Step 9.6: Factual audit (this workflow)
Step 10:  Final automated lint (em dashes, contractions, banned phrases)
```

All three must pass. Any failure rejects the output and returns to the agent with specific violations.

## Running the Audit

The audit can run as an LLM agent (Haiku or Sonnet reading the file and checking) OR as a grep-based script. Both are acceptable. For regular (daily) pipeline use, grep-based is preferred — deterministic, cheap, repeatable.

Grep-based implementation (sketch):
```bash
audit_file() {
  local F=$1
  local CV_SOURCE=/Users/yantram/Desktop/Pinaka_speckit/atma/people/shiva/wiki/cv.md
  local VIOLATIONS=0
  
  # Check 1
  if grep -iE "\\bI serve\\b|\\bserves .* customers\\b|\\bhandles \\d+|\\bruns \\d+ (concurrent|users)" "$F"; then
    echo "CHECK 1 FAIL: present-tense customer claim"
    ((VIOLATIONS++))
  fi
  # ... etc for checks 2-7
  
  if [ $VIOLATIONS -gt 0 ]; then
    return 1
  fi
  return 0
}
```

LLM-based implementation (more flexible):
Pass the file + cv.md to a Haiku agent with this workflow doc as the prompt. Agent returns structured report.

## Failure Modes

- **False positive (flags something that is actually true):** update the patterns or add the entity to an allowlist. Do not silently ignore.
- **False negative (misses a violation):** user catches in review; add pattern to checklist, flag as gap.
- **Agent refuses to fix after audit:** human steps in; the audit pointed at the problem, fix applies anyway.

## Known Limitations

- Does not catch subtle overclaims in prose (e.g., "built the entire AWS migration" when reality is "built the AWS migration with 2 engineers"). These require human judgment.
- Does not catch absent context (e.g., a true metric presented out of context that misleads).
- Patterns evolve. Review monthly during `/lint-atma` routine.
