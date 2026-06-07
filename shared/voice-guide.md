# Voice guide (craft layer)

The drafting brain reads this **before** writing any summary, bullet rewrite, or
cover letter. `shared/voice-rules.json` is the *machine gate* (banned words,
openers, em-dashes, contractions, word counts) — it catches form violations but
cannot judge craft. This file is the craft the code cannot check.

Ported and adapted from the Atma identity layer
(`atma/people/shiva/wiki/voice.md`, `atma/shared/ai-detection-guide.md`).

## Register

Direct, grounded, sharp. First-person. Specific numbers, no fluff.

* Short sentences next to longer explanation. Vary length deliberately —
  sameness reads as AI.
* "I tried X. It broke at Y. Here is the fix." Not "one might consider."
* Specific numbers, never qualifiers: "250K CCU", "7 to 10 minutes", "50K
  throttle" — never "large scale" or "optimized".
* Blunt. Willing to name a limitation or a past wrong call.
* Rough edges are a feature. Real tangents and uneven structure are
  authenticity signals.

## Core rule: reformulate, never regenerate

Start from a **verified fact** the candidate already has. Reword it to carry the
JD's vocabulary only where the new wording is a truthful description of the same
fact. Never generate a new achievement.

* Fact: "Built LLM workflows with retrieval-augmented generation."
* JD says: "RAG pipeline design."
* Write: "RAG pipeline design and deployment" — a reformulation of what is true.

If the JD needs something the library lacks, leave it uncovered. Never invent.

## The eight AI-detection tells (avoid all)

1. **Versatile-professional opening** — "Results-driven professional with a
   passion for innovation." No real person writes this.
2. **Uniform bullets** — every line "Achieved X by Y, resulting in Z%". Vary the
   shape: some start with a verb, some do not; one line, then two lines.
3. **Suspiciously round metrics** — 40%, 30%, 50%. Real data is messy: 58%,
   "~2x", "roughly 18 months". Use the real number or say "measurable".
4. **Vocabulary inflation** — spearheaded, orchestrated, pioneered, championed.
   Say built, led, fixed, shipped, worked with.
5. **Perfect keyword stuffing** — every JD term exactly once, evenly spread.
   Real experience repeats a tool because you actually used it in three roles.
6. **No specificity** — "collaborated with cross-functional teams to deliver
   user-centric solutions." Name the tool, the team size, the customer, the
   number.
7. **Skills section that lists everything** — 50 techs, half barely touched.
   List 15 to 20 you would defend in an interview, ordered by real use.
8. **Template-identical formatting** — perfect spacing, every section equal.
   Allow one small human imperfection (a slightly longer section, an unbolded
   word). Polish is itself a signal.

## Structure

* Lead with the point, not setup. First sentence delivers.
* Concrete anchor first: a person, a place, a number, a specific event.
* One idea per paragraph. Move on.
* Never open with a question. Never use symmetrical bullet lists. Never use
  predictable connectors (first/second/third, moreover/furthermore).

## Authenticity signals (require 3+ per drafted piece)

* A named, specific experience (a real person, place, or moment).
* A specific number tied to the point ("at 50K throttle, Cognito died").
* A line admitting a limitation or a past error.
* An opinion someone could disagree with.
* A named tool, place, or person — not a generic category.

## Honest-limitation move

Name the weakest evidence before the reader does, then reframe to the strength
that matters for this role. (Example pattern: "No formal sales-team experience.
What I have instead: I have run demos and POCs end to end, and I know the CFO
office from the inside.") This builds trust and preempts the obvious objection.

## Cover letters (when drafted)

1. Open on the buyer's problem, not the candidate's qualifications.
2. State the gap honestly, then pivot to the credential that matters here.
3. One concrete proof of technical credibility.
4. A specific first-90-days plan (two deliverables, prioritized).
5. One-line close offering a working session. No "I am writing to apply."

## Pre-send checklist

1. No em-dashes, no contractions, no banned words/openers (run the gate).
2. At least 3 authenticity signals present.
3. Sentence length varies; bullets are not all the same shape.
4. Numbers are real and messy, not suspiciously round.
5. The same key skill recurs naturally across roles (not stuffed once each).
6. One small human imperfection left in on purpose.
7. Opening line earns attention — no setup, no question.
