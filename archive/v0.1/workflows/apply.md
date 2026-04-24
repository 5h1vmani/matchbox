---
id: apply-workflow
purpose: Submit an application (human action), log to applications.md, write back to Atma log
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 2000_tokens
---

# Apply Workflow

Submit an application to a company, log the action to `applications.md`, and write an entry to Atma's `log.md`.

## Trigger

User decides to apply after reviewing a report in `reports/` and the tailored CV in `output/`.

## Manual Submission

Applications are NEVER automated. The human must click Apply on the company's ATS, submit via email, or otherwise directly interact with the company. Always.

This prevents spray-and-pray behavior and forces intentional review of each application.

## Multi-Application Hygiene (added 2026-04-20)

If applying to multiple roles at the same company in the same batch:

- Confirm no cover letter mentions "first preference is X" or any cross-reference to other applications. Silent is the rule.
- The recruiter will see all applications via the ATS and route accordingly. Cross-references in the letter create contradictions across the batch.
- When the recruiter calls (typical 7-14 days), have the multi-application explanation ready verbally: "Each fits different parts of my profile. I am comfortable letting your team route me where the fit is strongest."

## Pre-submit Checklist

Before clicking Apply, verify:

- [ ] Tailored CV read for AI tells (check `output/cv-{company-slug}-{YYYY-MM-DD}.pdf`)
- [ ] `atma/people/shiva/wiki/voice.md` compliance confirmed (no contractions, no em dashes, 3+ specificity signals)
- [ ] Cover letter drafted and reviewed (if required by JD)
- [ ] Contact details correct (email, phone) in CV
- [ ] Application method decided (portal, email, LinkedIn, recruiter)

## Post-submit Logging

### Update applications.md

Update the row for this opportunity:
- State: `evaluated` → `applied`
- Add submission date (today's date)
- Add method: email / portal / linkedin / recruiter
- Add application-specific notes (e.g., "applied via LinkedIn Easy Apply", "sent custom cover letter")

### Write-back to Atma

Declare Atma task: `ingest`

Propose an entry to `atma/people/shiva/wiki/log.md`:

```
target: log.md
title: YYYY-MM-DD: Applied to {Company} {Role}
evidence: [report](matchbox/people/shiva/reports/{NNN}-{slug}-{date}.md) + JD URL
duplicates_checked: yes (new application)
review_by: 30 days from submission
tag: [applied]

Body (2-3 lines):
{Brief description of role, key match points, and why you applied.}

Example:
"Applied to Anthropic Forward Deployed Engineer (India remote). Strong match: 5y+ systems engineering, LLM deployment experience, India location preference. Company vision aligns with career goal of working on AI safety at tier-1 org."
```

## State After Application

- `applications.md` shows state `applied` with submission date and method
- `atma/people/shiva/wiki/log.md` contains the application entry with evidence link
- Tailored CV saved at `output/cv-{company-slug}-{YYYY-MM-DD}.pdf`

## Follow-up Tracking

When company responds:
- Update `applications.md` to state `responded`
- Log brief response in applications.md notes

When interview is scheduled:
- Update `applications.md` to state `interview`
- Trigger `interview-prep.md` workflow to generate company-specific prep

## Critical Note

Applying without reviewing the tailored CV is the most common failure mode. Always read `output/cv-{company-slug}-{YYYY-MM-DD}.pdf` before clicking Apply. Reject if it reads as AI-generated, generic, or inaccurate.
