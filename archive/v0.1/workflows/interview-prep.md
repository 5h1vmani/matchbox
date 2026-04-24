---
id: interview-prep-workflow
purpose: Generate company-specific interview intelligence and map stories to likely questions
sensitivity: public
relevant_for: [all_tasks]
not_for: []
last_updated: 2026-04-19
review_by: 2026-10-19
size_budget: 2500_tokens
---

# Interview Prep Workflow

Generate company-specific interview intelligence, map STAR+R stories to likely questions, and compile a personalized prep guide.

## Trigger

User has an interview scheduled. Application state has transitioned from `responded` → `interview` in `applications.md`.

## Read Set (Atma Routing: interview_prep)

From `atma/people/{name}/routing.md`:

```yaml
always:    [story-bank.md, skills.md, cv.md]
sometimes: [projects.md, log.md#last-90d, narrative.md]
never:     [comp.md, network.md, writing-samples/*]
budget:    10000_tokens
```

## Research Phase (5 Queries, Never Invent)

Run these exact web searches. If a source says something, cite it. If inferring, mark `[inferred]`. Never fabricate questions or company details.

1. `"{company} {role} interview questions site:glassdoor.com"`
2. `"{company} interview process site:teamblind.com"`
3. `"{company} {role} interview site:leetcode.com/discuss"`
4. `"{company} engineering blog"`
5. `"{company} interview process {role}"` (general catch-all)

Return the exact URL and quoted text from each result.

## Process Overview

Synthesize findings into a single "Overview" section. Include:

- Number of interview rounds
- Total duration (days from first call to offer/rejection)
- Format of each round (video, phone, in-person, coding challenge)
- Difficulty rating (1-5, from Glassdoor if available)
- Positive experience rate (if available with source)
- Known quirks or red flags (with source citations)

All facts must have sources. No invented details.

## Round-by-round Breakdown

For each round identified:
- Duration (minutes)
- Conducted by (e.g., recruiter, hiring manager, team member, panel)
- What they evaluate (skills, culture fit, domain knowledge)
- Reported questions (list, with source and exact quote)
- How to prepare (specific actionable advice)

### Example

```
## Round 1: Recruiter Screen (30 min, phone)

Conducted by: Recruiter or hiring manager  
Evaluates: Communication, motivation, basic background fit

Reported questions (source: Glassdoor):
- "Tell us about your background"
- "Why are you interested in this role?"
- "What is your notice period?"

How to prepare:
- 2-minute narrative ready
- Three specific reasons why this company + role
- Salary expectations clarified (if asked)
```

## Likely Questions, Categorized

### Technical

List technical questions most relevant to the JD. If coding questions expected, mark difficulty (easy / medium / hard per LeetCode classification).

### Behavioral

- Shiva-specific red flags to address:
  - Gap in employment history / Isha role (explain exit story)
  - NTT DATA role to later roles (explain career progression rationale)
  - Unusual path (explain career pivots with clear motivation)

### Role-Specific

Questions tied directly to JD requirements. Example: if JD requires "3+ years Kubernetes," prepare for "Tell us about your Kubernetes production experience."

## Story Mapping Table

For each likely question, map to the best story from `atma/people/shiva/wiki/story-bank.md`. Columns:

| Question | Best Story | Fit (strong/partial/none) | Gap? |
|----------|-----------|--------------------------|------|
| "Tell us about a time you led a difficult project" | `Project Alpha - Q1 2026` | strong | none |
| "How do you handle ambiguity?" | `[story name]` | partial | needs new story, consider `log.md` entry from `{YYYY-MM-DD}` |

If gap exists, note "needs new story, consider expanding {specific log.md event} into STAR+R format."

## Technical Prep Checklist

Max 10 items, prioritized by research evidence. Examples:

- [ ] Review 3 LeetCode medium problems on {data_structure}
- [ ] Read company's last 2 blog posts on {technical_topic}
- [ ] Practice 2-min explainer for your largest project
- [ ] Code review 1 paper/talk from CTO or head of engineering
- [ ] Prepare 3 questions about their tech stack and roadmap

## Company Signals

### Values to Signal

Extract from company website, blog, job posting, Glassdoor. Examples: "customer-first", "shipping speed", "reliability culture".

### Vocabulary to Use

Technical terms or phrases from company materials. Mention these naturally in answers (without forcing).

### Things to Avoid

Language or approaches the company's values suggest are poor fits.

### 2-3 Sharp Questions to Ask Them

Research-backed questions that demonstrate deep understanding. Examples:

- "I noticed your blog post on {recent_architecture_change}, what were the key tradeoffs?"
- "What does success look like for this role after 6 months?"
- "How does your team approach technical debt?"

## Output

Path: `matchbox/people/{name}/output/interview-{company-slug}-{role-slug}-{YYYY-MM-DD}.md`

Format: Markdown with all sections above. Include source citations inline.

## Critical Rules

NEVER invent questions attributed to sources. If research returns sparse data:

- Broaden query to role archetype at similar-stage companies (Series A, Series B, etc.)
- Label inferred questions `[inferred from adjacent companies]`
- Acknowledge the limitation: "Limited public data for this company; these questions are typical for a {role_title} at {company_stage} companies."

Always cite sources. Unattributed claims are invalid.
