# Design brief — Discovery

> Hand to the design team. This briefs a **problem**, not a solution. The
> shipped Applications tracker (`designs/v1/`) is the standard, the system, and
> the proof you understand this product. Discovery is its sibling — a newer,
> harder problem. We want your thinking on *how it should work*, not just how it
> should look. We have opinions; we are deliberately not imposing them.

## Where it sits

Matchbox is a local-first, single-user job-search tool. One student moves through
three stages: **discover** roles → **tailor** a CV per role (an AI assistant does
the writing) → **track** applications (the tracker you built). Discovery is the
top of the funnel. Same student, same calm voice, same Oat system — it must feel
like one product with the tracker.

## The user

A single, **stressed job-seeker** — not a recruiter working a funnel. They are
based in India, and many roles they will see are geo-locked to other countries,
so *"you can't realistically apply to this"* is a frequent and important truth.

## The job to be done

> "Find roles I am actually a fit for and eligible for, without wasting my effort
> or drowning me."

Underneath it, in priority order:

1. Show me roles worth my attention — fresh, real, that I could actually get.
2. Tell me straight whether I am a fit, and whether I am even eligible — with the
   *reason*.
3. Let me decide fast, and never show me the same dead end twice.
4. Keep a trail of companies worth watching, even when there is no role today.

And the job beneath all of it — the one that decides whether this succeeds:
**reduce overwhelm and earn trust.** A surface that shows 200 real roles has
still failed.

## What the app knows about each role (your raw material)

For every role, the system can provide:

- company, title, location, remote, country, salary (sometimes), source, how
  recently it was posted, a link to the posting, and the full job description;
- a **fit** read — how well it matches the student's experience and targets, with
  a one-line reason;
- an **eligibility** read — whether they can realistically apply (geo / visa /
  lane), with an honest reason; *ineligible is common*;
- a **freshness** read — open, closing soon (with a date), or closed;
- optionally, how much of the role's must-haves the student's CV library already
  covers.

You decide what to show, when, and how. Nothing here is a required field on a
screen — it is simply what is available.

## The one hard constraint: the workflow

Discovery does not write CVs. The student triages here, then **delegates the
tailoring to an AI assistant** they run separately. So whatever you design, the
student must be able to:

- move a role into their **tracker** (it becomes a tracked item),
- **dismiss** roles they will not pursue (reversibly),
- hand a role, or a batch, to the **assistant** to tailor a CV.

How those are expressed is yours. The point: triage ends in a *decision* per
role, and one of those decisions is a hand-off.

## What good looks like

- A student opens this and within a couple of minutes knows what is worth
  pursuing today — without feeling behind or buried.
- They **trust the fit and eligibility calls** enough to act on them.
- An honest "you are probably not eligible" lands as *a kindness that saved them
  effort*, not a rejection.
- It feels calm, honest, and unmistakably the same hand that made the tracker.

## The hard problems — yours to solve

The interesting questions. This is where your expertise is worth the most:

- How should a student face a day's worth of incoming roles **without
  overwhelm**? (A feed? A queue? Something else entirely?)
- How do you present **fit and eligibility together, honestly** — so a role the
  student cannot get *saves* them time instead of discouraging them? This is the
  crux of the whole thing.
- How does a **closing or closed** role change its treatment?
- How does someone go from "this looks interesting" to "tailor this" with the
  least friction — and how does choosing a batch feel?
- How do they **explore and filter** (fit, eligibility, geo, freshness) without
  it turning into a database query — and never re-see what they dismissed?
- Is reading the full job description part of triage, or a separate, deeper
  moment?

## Voice

Same as the tracker: sentence case, no em dashes, second person, calm, honest, no
gamification. The honest no is *kind*, not clinical:

> "US-only role. You would need a visa, so probably not worth your time."

not "INELIGIBLE — location mismatch."

## Realities to design for

- A day where almost everything is ineligible (must not feel hopeless).
- A closed or expired role (truthful, not alarming).
- Nothing new today.
- First run, before any sources are connected.
- Roles missing a salary or a clean description.

## Out of scope

Three supporting surfaces are being built separately from your system, so you do
not need to design them: managing **sources** (where roles come from), browsing a
**companies** list (a large trail of recently funded startups), and a **runs /
activity** view (where the student watches work handed to the assistant). For
context, the product's sidebar today is Today · Applications · Insights, with
discovery, companies, sources, and runs joining it — but how discovery itself is
shaped is open.

## How we would like to work

Come back with **2–3 directions** for how discovery could work — divergent, not
one polished answer — as interactive Oat prototypes (React 18 + your CSS is
fine). We will react with product judgment and converge together; the chosen
direction then gets the engineering-handoff treatment, like the tracker.

We can give you the **real student and the real roles** to design against. Ask
for them, and use them — that is worth more than any spec.

## Reference

The tracker in `designs/v1/` is the bar and the system. Match it. Beyond that,
the surface is yours to invent.
