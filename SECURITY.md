# Security Policy

## Threat model

Matchbox is a **single-user local tool**. The threat model is "my own machine, my own network," not "untrusted users on the internet." The dashboard binds to `127.0.0.1` by default and has:

* No authentication.
* No CSRF protection.
* No rate limiting.

If you expose Matchbox beyond loopback, you are responsible for the auth and access-control layer in front of it.

One boundary deserves a callout: the reasoning engine (Claude Code) reads
scraped job descriptions and the files you drop into `inbox/`. Treat both
as untrusted input. The agent instructions say so explicitly, and the
deterministic core limits the blast radius: CV content can only be
selected from facts you verified, every id is validated, and rendering
never executes anything from a JD. A malicious job posting can waste a
tailoring run; it cannot put words on your CV.

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.**

Use one of these private channels:

1. **Preferred:** open a [private security advisory](https://github.com/5h1vmani/matchbox/security/advisories/new) on this repository. GitHub will send only the maintainers a notification.
2. Alternatively, email the maintainer directly through the contact listed on their GitHub profile.

Please include:

* A description of the issue
* Steps to reproduce
* The version (`matchbox --help` shows it, or `pyproject.toml`)
* Your assessment of impact and exploitability

We aim to acknowledge reports within **3 business days** and provide a triage decision within **7 business days**. We're a small project. If you don't hear back in that window, please ping again.

## Scope

In scope:

* Path traversal, injection, or input-handling bugs in the web layer
* Cost-confirmation bypass (anything that lets a request spend Anthropic API budget without the documented confirmation flow)
* Profile data leakage between profiles on the same machine
* Issues in the bundled dependencies (please report upstream too)

Out of scope:

* "No auth on a localhost binding" (documented and intended; see [docs/decisions/0005](docs/decisions/0005-no-auth-localhost-only.md))
* Issues that require already-compromised local access
* Vulnerabilities in third-party services (Anthropic, GitHub, etc.): please report them to those vendors directly

## Disclosure policy

We follow **coordinated disclosure**:

1. We confirm and reproduce the report.
2. We develop a fix and prepare a release.
3. We coordinate a public disclosure date with the reporter (typically 30–90 days after fix is available).
4. We credit the reporter in the release notes unless they request otherwise.

## Hardening tips for self-hosting

If you must expose Matchbox beyond your local machine:

* Put it behind a reverse proxy with auth ([Caddy + basic-auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth) is the lowest-effort path).
* Use [Tailscale](https://tailscale.com) instead of public exposure.
* Set `MATCHBOX_COST_CONFIRM_USD` to a small value (e.g., `0.01`) so every tailor requires explicit confirmation.
* Keep `ANTHROPIC_API_KEY` in a separate file (`.env` is gitignored), never in shell history.
* Run `pre-commit install` so PII / secret detection catches accidental commits before push.

## Supported versions

We support the latest minor release on the `main` branch. Older versions receive no security updates. Pin to a tag if you need stability.

| Version | Supported |
|---------|-----------|
| 0.4.x | ✅ |
| 0.3.x | ❌ (upgrade, no security backports) |
| < 0.3 | ❌ |
