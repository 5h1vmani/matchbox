# 0002. HTMX + Jinja over React or Streamlit

* Status: accepted
* Date: 2026-04-26
* Supersedes: implicit choice of Streamlit in v0.2
* Tags: web, architecture

## Context

The v0.2 dashboard was Streamlit. As the UX problems list grew (triage table that scales, multi-select bulk actions, Cmd+K palette, optimistic UI, cost-confirmation modals, live re-score preview), Streamlit's whole-script-rerun model was becoming the bottleneck. Every interaction reran the page.

Three realistic alternatives were on the table for the rebuild: stay with Streamlit, switch to HTMX, or switch to React + a JSON API.

## Decision

**HTMX + FastAPI + Jinja + Tailwind (via CDN).** Specifically:

* Server renders HTML.
* HTMX swaps partials in response to user actions; whole-page reloads only at first load.
* Alpine.js handles tiny client state (modal open/close, slider sums).
* Tailwind via Play CDN — no Node toolchain.
* Backend stays 100% Python.

## Consequences

**Good:**

* Targeted DOM swaps fix Streamlit's biggest problem (re-render-everything on every interaction).
* No npm, no build step, no API contract to maintain.
* Backend types flow directly into templates via `Jinja2Templates` + Pydantic.
* Inline PDF preview via plain `<iframe>` — trivially.
* URL routing is free; bookmarkable filters are free.
* One language (Python) for everything that matters.

**Bad:**

* We give up React's component-library ecosystem (no shadcn/Radix). Tailwind covers ~80% of styling needs.
* Charts are not a Streamlit one-liner. We build them by hand (currently small SVG/text); if we ever need rich charts, we'll add Chart.js as a CDN script.
* Tailwind Play CDN doesn't process `@apply`. Custom rules go in `static/style.css` directly.
* Complex client-state interactions (drag-drop reorder, multi-step wizards) are awkward. We don't have any today.

## Alternatives considered

* **Stay with Streamlit.** Lowest cost. Lost because the planned UX work would be fighting the framework on every feature. The single bug "star click re-renders 500 jobs" is the canary.
* **React + FastAPI + JSON API.** Highest UX ceiling. Lost because of the maintenance burden: two ecosystems forever, an API contract to design and version, type duplication (Pydantic → TS), Node toolchain, build step. Unjustified for a single-user local tool.
* **Reflex / NiceGUI / Solara (Python-native React-y).** Tempting in theory. Lost because we'd be debugging compiled output of small-community frameworks. Streamlit's flaws are at least well-known; these projects' flaws live in 2024 GitHub issues with three thumbs-up.
* **Datasette.** Designed for read-mostly SQLite browsing. Lost because mutating actions (star, apply, log-response) require custom plugins, and the UX for tailor cost gates would be awkward.
* **Textual TUI.** Considered for a power-user terminal interface. Lost because PDF preview is impossible and outcome-logging-by-keyboard is no faster than the web with shortcuts.

## References

* The 2-hour spike that validated the choice: see commit history around the v0.3 rebuild.
* [HTMX rationale](https://htmx.org/essays/) — particularly "Hypermedia-Driven Applications".
