# 0004. LLM only for judgment, code for transformation

* Status: accepted
* Date: 2026-04-21
* Tags: cost, architecture, llm

## Context

Early Matchbox builds used the LLM for everything in the tailor pipeline: extracting JD requirements, picking bullets, rewriting prose, formatting markdown, embedding fonts, base64-encoding images, emitting HTML. A single tailored CV cost ~$0.50–$2 in API calls and took 30+ seconds.

Analysis (see [history/2026-04-21-cost-optimization.md](../history/2026-04-21-cost-optimization.md)) showed roughly:

* ~20% of the work was real *judgment*: which bullets to pick, what tone to use, how to phrase a transition.
* ~80% was *transformation*: template substitution, regex linting, file I/O, layout.

We were paying LLM pricing for 100% of it.

## Decision

LLM is called exactly **once per non-canonical application**, via a single tool-use call that returns structured JSON. Everything before (anchor pack lookup, prompt construction) and after (template substitution, gate checks, Typst render) is deterministic Python.

For canonical-tier jobs, the LLM is not called at all — a pre-rendered PDF is copied.

## Consequences

**Good:**

* Cost-per-tailor dropped roughly 5×.
* Determinism: gate violations are reproducible; we don't ask the LLM "is this OK?" we *check*.
* Faster: most of the time is now Typst render (~2s), not API round-trip.
* Easier to test: the tailor module's deterministic parts have unit tests; the LLM call has a single integration test.
* Failure modes are localised: if the LLM fails, we know exactly what step.

**Bad:**

* Adding a new "judgment" step requires deliberate decision: do we *really* need the LLM for this? Resisting easy uses is constant friction.
* Anchor packs need maintenance — they're the human-curated raw material the LLM picks from. Adding a new role family is real work.

## Alternatives considered

* **Multi-step LLM chain.** A "planner" LLM call, then a "writer" LLM call, then a "linter" LLM call. Rejected — each call costs and adds latency; gate checks can be deterministic; the planner role can be a hardcoded prompt structure.
* **Smaller / cheaper model.** Considered Haiku for the judgment call. The quality drop on bullet rewriting was visible. We use Haiku for high-throughput reads (e.g., scoring assists in future) but not for the single judgment call.
* **No LLM at all** (canonical for everything). Considered for v0.1. Rejected because the bespoke tier is where high-value applications happen — those are worth $14 to win an interview at a target company.

## References

* [history/2026-04-21-cost-optimization.md](../history/2026-04-21-cost-optimization.md) — the analysis that produced this rule.
* [history/2026-04-21-blind-spots.md](../history/2026-04-21-blind-spots.md) — the meta-reflection on whether even this was the right thing to optimise.
