# 0007. Pre-commit hooks: defer the strictness tier

* Status: accepted
* Date: 2026-04-24
* Tags: tooling, process

## Context

Pre-commit hooks fall into three useful tiers:

1. **Auto-fix** (silent, never blocks): formatters, EOF fixers, JSON validators.
2. **Security** (blocks disasters, near-zero false positives): secret scanners, PII regex, API-key detectors.
3. **Strictness** (high-friction, frequent false positives): mypy --strict, conventional-commit message lint, full pytest run on push.

We have tier 1 and tier 2 in place. Tier 3 is the one under question.

## Decision

**Defer the strictness tier until the product stabilises.** Specifically: no pytest-on-push hook, no commit-message format hook, no "must be on the latest mypy" hook.

We *do* run `mypy --strict` as a pre-commit hook (because it mirrors CI exactly and catches genuine type errors fast); we do *not* add it as a slow pre-push hook.

## Consequences

**Good:**

* During fast prototyping, we don't fight the hooks. PRs land quickly.
* `--no-verify` doesn't become muscle memory because the hooks that *do* run have near-zero false positives.
* CI still catches everything the strictness tier would catch; we just catch it on PR review instead of on commit.

**Bad:**

* Bad commit messages slip in. Reviewers ask for fixups during PR review instead of pre-commit catching them.
* Someone could push code that fails CI and discover it minutes later. CI runtime is < 30s, so this is a small cost.

## When to revisit

* After Phase 3.1 ships (the first real tailored application end-to-end), product shape stabilises and the cost-benefit of strict hooks tilts.
* If `--no-verify` shows up in commit messages, that's the signal that the existing hooks are too noisy — fix them, don't add more.

## What this rules out

* A `commit-msg` hook enforcing Conventional Commits. (CI doesn't enforce either; reviewers do.)
* A pre-push hook running the full pytest suite. (CI runs it on every push, no point doubling up.)
* A documentation lint that blocks merge if a `docs/*.md` is missing for a `feat`. (Reviewers check.)

## Alternatives considered

* **Ship the strictness tier now.** Rejected — too early in the product's life. We're still rewriting modules wholesale; high-friction hooks penalise that.
* **Make strictness opt-in via a separate hook stage.** Considered. Rejected because no one opts in voluntarily; it'd be dead config.

## References

* `.pre-commit-config.yaml` — current hook list.
* `CONTRIBUTING.md` — the four checks we enforce by convention.
