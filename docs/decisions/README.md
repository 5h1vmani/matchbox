# Architectural Decision Records (ADRs)

> An ADR is a one-page record of an architectural choice we've made, the alternatives we considered, and why we picked what we picked. Read these before proposing changes that contradict them.

We follow a lightweight version of the [MADR](https://adr.github.io/madr/) format. Each ADR is:

```text
0NNN-short-kebab-title.md

# 0NNN. Title

* Status: accepted | superseded by 0NNN | deprecated
* Date: YYYY-MM-DD
* Deciders: who approved
* Tags: optional comma-separated tags

## Context

What forced the decision? What constraints?

## Decision

What we chose, in one paragraph.

## Consequences

Good and bad. Be honest about the trade-offs.

## Alternatives considered

Brief — one paragraph each. Why we didn't pick them.

## References

Links to discussions, prior art.
```

## Numbering

Monotonically increasing 4-digit prefix. Don't reuse numbers. If a decision is reversed, write a new ADR that supersedes the old one — never edit the old one's body.

## Index

| #    | Title                                                                | Status     |
|------|----------------------------------------------------------------------|------------|
| 0001 | [CLI and web are equal partners](0001-cli-and-web-as-equal-partners.md) | accepted   |
| 0002 | [HTMX + Jinja over React or Streamlit](0002-htmx-over-react.md)         | accepted   |
| 0003 | [SQLite per profile, not a shared DB](0003-sqlite-per-profile.md)      | accepted   |
| 0004 | [LLM only for judgment, not transformation](0004-llm-only-for-judgment.md) | accepted |
| 0005 | [No auth — localhost-only by design](0005-no-auth-localhost-only.md)   | accepted   |
| 0006 | [Rename ScoringWeights to align with Job dimensions](0006-scoring-weight-rename.md) | accepted |
| 0007 | [Pre-commit hooks: defer the strictness tier](0007-no-strictness-hooks-yet.md) | accepted |
