# 0003. SQLite per profile, not a shared DB

* Status: accepted
* Date: 2026-04-21
* Tags: data, architecture

## Context

Matchbox tracks jobs, responses, and scan runs. Two reasonable storage layouts:

1. **One DB shared across all profiles**, with a `profile_name` column on every table.
2. **One DB per profile**, at `people/{name}/db.sqlite`.

## Decision

One SQLite file per profile.

## Consequences

**Good:**

* Cross-profile contamination is structurally impossible. Alice's jobs cannot bleed into Bob's because they live in different files.
* Backup and portability are trivial: `cp -r people/alice/ /backup/`. Hand a profile to a friend with `tar`.
* Schema migrations are per-profile; one corrupted profile doesn't block the others.
* The `db.list_jobs(profile, ...)` call always opens the right file — no chance of forgetting a `WHERE profile_name=?`.
* Per-profile size stays small even after years of jobs (each profile is independent).

**Bad:**

* No "give me everyone's stats" query. We don't need it (single-user tool), but if we ever did we'd need to walk all profiles.
* More file handles open over time. SQLite caches connections per profile; in practice this hasn't been an issue at the scale of one user.
* Two profiles with the same job URL get two row IDs. Deduplication is per-profile only.

## Alternatives considered

* **Single shared DB with `profile_name` column.** Rejected — every query needs a `WHERE profile_name=?` and forgetting one is a privacy bug.
* **Per-profile JSON files.** Rejected — we want SQL filtering for the inbox at 500+ jobs.
* **External database (Postgres).** Massive overkill for a single-user tool. Rejected.

## References

* `src/matchbox/core/db.py` is the only module with `import sqlite3`; this ADR is enforced by code review and an SSOT rule in CONTRIBUTING.md.
