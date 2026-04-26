# Setup

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | [python.org](https://python.org) |
| uv | latest | `curl -Lsf https://astral.sh/uv/install.sh \| sh` |
| Typst | 0.11+ | `cargo install typst-cli` or [typst.app](https://typst.app) |
| Anthropic API key | — | [console.anthropic.com](https://console.anthropic.com) |

## Install

```bash
git clone <repo-url> matchbox
cd matchbox

# With uv (recommended)
uv sync --dev

# Or with pip
pip install -e ".[dev]"
```

## API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# Or add to .env (gitignored):
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

The tailor step is the only place that calls the API.
Scan, score, and tracking are all free.

## Verify install

```bash
matchbox --help
matchbox scan shiva --dry-run
```

## Web dashboard

```bash
matchbox web                 # http://127.0.0.1:8765
matchbox web --port 9000     # custom port
matchbox web --reload        # auto-reload on code changes (dev)
```

The dashboard is FastAPI + HTMX + Tailwind — no build step.
Use `matchbox seed-demo` to populate the demo profile with 30 synthetic jobs
so you can see the UI in action before connecting an API key.

> **Security:** the dashboard has no auth, no CSRF protection, and no rate
> limiting. It binds to `127.0.0.1` by default. **Do not** expose to the
> network. The CLI prints a warning if you set `--host` to anything else;
> heed it.

## Typst (for PDF generation)

Typst is only needed for `matchbox tailor` and `matchbox rebuild-canonicals`.
If you skip it, scan + score + tracking still work.

```bash
# macOS (Homebrew)
brew install typst

# Cargo
cargo install typst-cli

# Verify
typst --version
```

## First scan

```bash
# Dry run — probes ATS boards, scores jobs, prints counts but writes nothing
matchbox scan shiva --dry-run

# Real scan (writes to people/shiva/db.sqlite)
matchbox scan shiva

# UK-only
matchbox scan shiva --country uk
```

## First tailor

```bash
# List top-scored jobs
matchbox score-job shiva 1

# Tailor job #42 (bespoke or template — canonical copies the pre-rendered PDF)
matchbox tailor shiva 42

# Rebuild canonical PDFs (prerequisite for canonical-tier applications)
matchbox rebuild-canonicals shiva
```

## Database

Each profile has its own SQLite DB at `people/{name}/db.sqlite` (gitignored).
Schema is created idempotently on first use — no migration step needed.

```bash
# Inspect directly
sqlite3 people/shiva/db.sqlite "SELECT company, role, total_score, state FROM jobs ORDER BY total_score DESC LIMIT 20"
```

## Running tests

```bash
pytest
pytest -q           # quiet
pytest -k "shiva"   # filter
```
