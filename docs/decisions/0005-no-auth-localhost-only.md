# 0005. No auth — localhost-only by design

* Status: accepted
* Date: 2026-04-26
* Tags: security, scope

## Context

Matchbox is a personal tool. The dashboard binds to `127.0.0.1` and is intended to be run on the user's own laptop. We considered adding auth (basic-auth, session cookies, OAuth) so the tool could be safely exposed beyond loopback.

## Decision

**No auth.** No CSRF protection. No rate limiting. The dashboard binds to `127.0.0.1` by default. The CLI prints a red warning if `--host` is set to anything else.

If a user wants remote access, they put it behind a reverse proxy with auth (Caddy + basic-auth, Tailscale, etc.) — that's their responsibility, not ours.

## Consequences

**Good:**

* No authentication code surface to maintain or audit.
* No password storage, no session management, no OAuth client setup.
* The user model stays simple: "you and only you".
* Adding "share my profile with a teammate" requires explicit user setup; we never accidentally leak data because we forgot a check.

**Bad:**

* Self-hosting for a small team is a bring-your-own-auth exercise. We document the recipe in [SECURITY.md](../../SECURITY.md) but don't ship it.
* Anyone who can reach the port can spend the user's API budget. Mitigations: 127.0.0.1 binding, server-enforced cost confirmation above threshold, bulk-tailor cap.

## Alternatives considered

* **Built-in basic auth.** Rejected — gives a false sense of security; basic-auth without TLS is plaintext over the wire; users who care will use a reverse proxy anyway.
* **Session-based auth with a SQLite session table.** Rejected — adds significant code surface for a single-user tool. Maintenance burden forever.
* **Magic-link auth via email.** Hilariously overkill.

## What we *do* defend against

Even on localhost, we still defend against accidents:

* Profile-name path parameter validated by regex + dir-exists check (no path traversal).
* File serving restricted to `people/{p}/output/{id}/{name}.{pdf|png}` with double-resolve guard.
* Server-enforced cost confirmation above `MATCHBOX_COST_CONFIRM_USD` for any LLM call.
* Bulk-tailor cap (`MAX_BULK_TAILOR = 5`).

These prevent foot-shooting, not malicious attackers.

## References

* [SECURITY.md](../../SECURITY.md) — full threat model and self-hosting hardening guide.
* The CLI warning in `cli.py:web()` — read it before changing.
