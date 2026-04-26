# Documentation index

Everything that's not the README. Each doc is the SSOT for its scope — when something is true in the code, exactly one doc says so.

## For users

| Doc | When to read it |
|---|---|
| [setup.md](setup.md) | Installing, prerequisites, verifying it works |
| [operator-runbook.md](operator-runbook.md) | Daily commands once you're running |
| [cli-reference.md](cli-reference.md) | Every CLI command + every flag |
| [troubleshooting.md](troubleshooting.md) | Things that go wrong, with fixes |

## For contributors

| Doc | When to read it |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Before opening your first PR |
| [development.md](development.md) | Local dev workflow, releasing, debugging |
| [architecture.md](architecture.md) | Module map, data flow, scoring + gates |
| [ux-design.md](ux-design.md) | Why the dashboard looks the way it does |
| [decisions/](decisions/) | Architectural decision records (ADRs) |

## Reference

| Doc | What it is |
|---|---|
| [../CHANGELOG.md](../CHANGELOG.md) | Release history, semver-tracked |
| [../SECURITY.md](../SECURITY.md) | Threat model + how to report vulnerabilities |
| [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community standards (Contributor Covenant 2.1) |
| [history/](history/) | Snapshots of past thinking — not maintained |

## Where to look first when…

* **You're new and want to see the UI:** [setup.md](setup.md) — `pip install`, `matchbox seed-demo`, `matchbox web`. 60 seconds.
* **You want to know how to run it daily:** [operator-runbook.md](operator-runbook.md).
* **The dashboard looks wrong:** [troubleshooting.md](troubleshooting.md).
* **You want to know why something is the way it is:** [decisions/](decisions/) first, then [architecture.md](architecture.md).
* **You want to add a feature or send a PR:** [../CONTRIBUTING.md](../CONTRIBUTING.md), then [development.md](development.md).
* **You found a security bug:** **don't** open a public issue — [../SECURITY.md](../SECURITY.md).

## Doc conventions (docs-as-code)

* All docs are Markdown, lint-checked by `markdownlint` in pre-commit and CI.
* Internal links are relative file paths so they work on GitHub *and* in any docs viewer.
* Code blocks specify a language (` ```bash `, ` ```python `, ` ```text `) — `markdownlint-MD040` enforces this.
* One H1 per doc; section structure flows H2 → H3.
* No marketing prose. State the thing, give an example, move on.
* When the code changes, the doc changes in the same PR. CI doesn't enforce this yet but reviewers do.
