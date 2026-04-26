# 0001. CLI and web are equal partners

* Status: accepted
* Date: 2026-04-26
* Tags: architecture, ux

## Context

Matchbox started as a CLI. The web dashboard came later. The natural drift in projects with both surfaces is that one becomes "real" and the other becomes a thin wrapper or an afterthought. That asymmetry causes:

* Subtle behaviour drift between surfaces (a bulk action does X via CLI but Y via web).
* Tests written only against one surface, missing bugs in the other.
* New features added to one and forgotten in the other.

## Decision

Both surfaces are first-class. Both call the same `matchbox.*` modules. Specifically:

* The web layer is a **thin adapter** over the same primitives the CLI uses. It does not reach into the database directly; it goes through `matchbox.core.db`.
* Where there is genuinely web-only concern (cost preview UI, gate-violation surface, palette search), it lives in `web/*_view.py` modules whose names end in `_view` to mark them as adapter code.
* The CLI is the durable interface. UI frameworks change. The CLI is what you script against, what tests use, what survives a UI rewrite.

## Consequences

**Good:**

* Tests cover both surfaces because the underlying primitive is the same.
* Switching UI frameworks costs only the UI — the CLI never moved.
* New users can start with the web; advanced users can script with the CLI; both get the same behaviour.

**Bad:**

* Some web-specific UX (live re-score preview, optimistic toggles) requires extra plumbing in `web/*_view.py` instead of being a single template.
* We resist adding "web-only" features that would be natural to add inline.

## Alternatives considered

* **Web is primary, CLI is wrapping.** Common in modern tools. We rejected because we want headless `matchbox scan` in cron, no browser, no JS runtime.
* **CLI is primary, web is read-only.** Considered. Lost because outcome logging in 1-click is the single biggest UX win, and that requires web mutation.

## References

* See [docs/ux-design.md](../ux-design.md) "two users" section for the user model that drives this.
