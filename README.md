# Matchbox

[![CI](https://github.com/5h1vmani/matchbox/actions/workflows/ci.yml/badge.svg)](https://github.com/5h1vmani/matchbox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Type checked: mypy strict](https://img.shields.io/badge/type%20checked-mypy%20strict-2bbc8a.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/lint%20%2B%20format-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Conventional Commits](https://img.shields.io/badge/commits-conventional-fe5196.svg)](https://www.conventionalcommits.org)

> Precision job-application pipeline. Scan ATS boards → score by fit → tailor at the right cost tier → track outcomes.

Single-machine CLI + web dashboard. Your data stays on your laptop. The only network call is the optional Anthropic API for tailoring high-scoring jobs.

## What it does

| Step | Command | Cost |
|------|---------|------|
| Scan 20+ ATS boards (Greenhouse / Lever / Ashby / Workable) | `matchbox scan alice` | $0 |
| Score each job on 6 dimensions (deterministic, no LLM) | automatic | $0 |
| Route to bespoke / template / canonical / skip | automatic | $0 |
| Generate tailored CV + cover letter | `matchbox tailor alice 42` | $0–$20 |
| Track outcomes (interview / offer / rejection) | one click in the web UI | $0 |
| Conversion funnel + cost-per-stage analytics | `matchbox analytics alice` or **Insights** page | $0 |

## 60-second demo (no API key, no profile setup)

```bash
git clone https://github.com/5h1vmani/matchbox.git
cd matchbox
pip install -e ".[dev]"

matchbox seed-demo            # 30 synthetic jobs in people/demo/
matchbox web                  # http://127.0.0.1:8765
```

Click around. Press `?` for shortcuts, `⌘K` for the command palette. **Zero spend.**

## Real usage

```bash
matchbox init-profile alice                 # creates people/alice/ with starter YAML
$EDITOR people/alice/profile.yaml           # candidate, target roles, weights, ...
$EDITOR people/alice/stories.md             # 3-5 STAR+R career stories

export ANTHROPIC_API_KEY=sk-ant-...         # only needed for `tailor`
matchbox scan alice                         # populate people/alice/db.sqlite
matchbox web                                # triage in the browser
```

Full install (Typst, uv, env vars): see **[docs/setup.md](docs/setup.md)**.

## Tier routing

| Score (0–5) | Tier | Action | Estimated cost |
|---|---|---|---|
| ≥ 4.0 | `bespoke` | Full Sonnet rewrite from anchor packs | $10–20 |
| ≥ 3.0 | `template` | Lighter Sonnet prompt + anchor pack | $0.05–0.30 |
| ≥ 2.0 | `canonical` | Copy a pre-rendered PDF | $0 |
| < 2.0 | `skip` | No output | $0 |

The UI **never spends money silently.** Above the configurable `MATCHBOX_COST_CONFIRM_USD` threshold (default $1) you must explicitly confirm. Bulk tailor is capped at 5 jobs in the UI; for batches use the CLI.

## Repository layout

```text
matchbox/
├── src/matchbox/
│   ├── core/          # Pydantic schema, SQLite layer, person loader
│   ├── scoring/       # Exclusions, 6-dim rubric, tier router
│   ├── discovery/     # ATS probers, daily scan, funding scan
│   ├── tailor/        # Quality gates, content gen, Typst render, dispatch
│   ├── outcome/       # Response logging, follow-ups, analytics
│   ├── web/           # FastAPI + HTMX + Jinja + Tailwind dashboard
│   └── cli.py         # Typer entry point
├── people/
│   ├── demo/          # Demo profile (committed, gets you running in 30s)
│   └── {your_name}/   # Your real profile (gitignored automatically)
├── shared/
│   ├── rubric.yaml             # 6-dimension scoring weights
│   ├── voice-rules.yaml        # Universal voice constraints
│   └── templates/              # Typst CV + cover letter templates
├── tests/                       # 109 tests; ruff + mypy strict + pytest in CI
└── docs/                        # See docs/index.md
```

## Documentation

* **[Setup](docs/setup.md)** — install, prerequisites, verifying
* **[Operator runbook](docs/operator-runbook.md)** — daily commands
* **[Architecture](docs/architecture.md)** — module map, data flow, gates
* **[UX design rationale](docs/ux-design.md)** — *why* the dashboard looks the way it does
* **[CLI reference](docs/cli-reference.md)** — every command + flags
* **[Troubleshooting](docs/troubleshooting.md)** — common errors
* **[Decision records (ADRs)](docs/decisions/)** — durable architectural choices
* **[Contributing](CONTRIBUTING.md)** — code standards, PR flow
* **[Development guide](docs/development.md)** — local dev workflow
* **[Changelog](CHANGELOG.md)** — release history
* **[Security policy](SECURITY.md)** — how to report vulnerabilities
* **[Code of conduct](CODE_OF_CONDUCT.md)** — community standards

Full index at **[docs/index.md](docs/index.md)**.

## Security

Matchbox is a **single-user local tool**: no auth, no CSRF protection, no rate limiting. The web dashboard binds to `127.0.0.1` only by default. **Do not** expose it to the network without a reverse proxy + auth — anyone who can reach the port can read your jobs and spend your Anthropic API budget.

To report a security issue, see [SECURITY.md](SECURITY.md). Please do not open a public issue.

## Contributing

PRs welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) — short version: ruff + mypy strict + pytest must pass, conventional commits, no PII in commits.

## License

MIT — see [LICENSE](LICENSE).
